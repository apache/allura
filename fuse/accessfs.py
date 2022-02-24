#!/usr/bin/env python

#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

import os
import json
import six.moves.urllib.request
import six.moves.urllib.parse
import six.moves.urllib.error
import sys
import pwd
import errno
import fcntl
import logging
import time

from threading import Lock
from collections import deque

import fuse
import six

log = logging.getLogger(__name__)

logging.basicConfig()

fuse.fuse_python_api = (0, 2)
fuse.feature_assert('stateful_files', 'has_init')


class check_access:

    def __init__(self, *args, **kwargs):
        self._args = args
        self._kwargs = kwargs

    def __call__(self, func):
        def wrapper(inst, *args, **kwargs):
            new_args = list(args)
            new_kwargs = dict(kwargs)
            for i, (mode, path) in enumerate(zip(self._args, args)):
                new_args[i] = self.check(inst, path, mode)
            for name, mode in self._kwargs.items():
                new_kwargs[name] = self.check(inst, kwargs.get(name), mode)
            return func(inst, *new_args, **new_kwargs)
        return wrapper

    def check(self, inst, path, mode):
        if mode is None:
            return
        rc = inst.access(path, mode)
        if rc:
            raise OSError(errno.EPERM, path, 'Permission denied')


class check_and_translate(check_access):

    def check(self, inst, path, mode):
        super().check(inst, path, mode)
        return inst._to_global(path)


def flag2mode(flags):
    md = {os.O_RDONLY: 'r', os.O_WRONLY: 'w', os.O_RDWR: 'w+'}
    m = md[flags & (os.O_RDONLY | os.O_WRONLY | os.O_RDWR)]
    if flags | os.O_APPEND:
        m = m.replace('w', 'a', 1)
    return m


class AccessFS(fuse.Fuse):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.root = '/'
        self.auth_method = 'unix'
        self.permission_host = 'http://localhost:8080'
        self.permission_cache_timeout = 30
        self.permission_cache_size = 1024
        self.file_class = self.make_file_class()
        self.perm_cache = None

    def getattr(self, path):
        return os.lstat("." + path)

    def readlink(self, path):
        self._assert_access(path, os.R_OK)
        return os.readlink("." + path)

    def readdir(self, path, offset):
        print('Readdir!')
        for e in os.listdir("." + path):
            yield fuse.Direntry(e)

    def unlink(self, path):
        self._assert_access(path, os.W_OK)
        os.unlink("." + path)

    def rmdir(self, path):
        self._assert_access(path, os.W_OK)
        os.rmdir("." + path)

    def symlink(self, path, path1):
        self._assert_access(path, os.W_OK)
        os.symlink(path, "." + path1)

    def rename(self, path, path1):
        self._assert_access(path, os.R_OK | os.W_OK)
        self._assert_access(path1, os.R_OK | os.W_OK)
        os.rename("." + path, "." + path1)

    def link(self, path, path1):
        self._assert_access(path, os.R_OK)
        self._assert_access(path1, os.W_OK)
        os.link("." + path, "." + path1)

    def chmod(self, path, mode):
        self._assert_access(path, os.W_OK)
        os.chmod("." + path, mode)

    def chown(self, path, user, group):
        self._assert_access(path, os.W_OK)
        os.chown("." + path, user, group)

    def truncate(self, path, len):
        self._assert_access(path, os.W_OK)
        f = open("." + path, "a")
        f.truncate(len)
        f.close()

    def mknod(self, path, mode, dev):
        self._assert_access(path, os.W_OK)
        os.mknod("." + path, mode, dev)

    def mkdir(self, path, mode):
        self._assert_access(path, os.W_OK)
        os.mkdir("." + path, mode)

    def utime(self, path, times):
        os.utime("." + path, times)

    def access(self, path, mode):
        if mode & (os.R_OK | os.W_OK) == 0:
            return
        ctx = fuse.FuseGetContext()
        entry = self.perm_cache.get(ctx['uid'], path)
        if (mode & entry) != mode:
            return -errno.EACCES

    def _assert_access(self, path, mode):
        rc = self.access(path, mode)
        if rc:
            raise OSError(errno.EPERM, path, 'Permission denied')

    def statfs(self):
        """
        Should return an object with statvfs attributes (f_bsize, f_frsize...).
        Eg., the return value of os.statvfs() is such a thing (since py 2.2).
        If you are not reusing an existing statvfs object, start with
        fuse.StatVFS(), and define the attributes.

        To provide usable information (ie., you want sensible df(1)
        output, you are suggested to specify the following attributes:

            - f_bsize - preferred size of file blocks, in bytes
            - f_frsize - fundamental size of file blcoks, in bytes
                [if you have no idea, use the same as blocksize]
            - f_blocks - total number of blocks in the filesystem
            - f_bfree - number of free blocks
            - f_files - total number of file inodes
            - f_ffree - nunber of free file inodes
        """

        return os.statvfs(".")

    def fsinit(self):
        uid_cache = UnixUsernameCache()
        self.perm_cache = PermissionCache(
            uid_cache,
            self.permission_host,
            self.permission_cache_timeout,
            self.permission_cache_size)
        os.chdir(self.root)

    def make_file_class(self):
        class FSAccessFile(AccessFile):
            filesystem = self
        return FSAccessFile


class AccessFile(fuse.FuseFileInfo):
    direct_io = False
    keep_cache = False
    needs_write = (
        os.O_WRONLY
        | os.O_RDWR
        | os.O_APPEND
        | os.O_CREAT
        | os.O_TRUNC)

    def __init__(self, path, flags, *mode):
        access_mode = os.R_OK
        if flags & self.needs_write:
            access_mode |= os.W_OK
        self.filesystem._assert_access(path, access_mode)
        self.file = os.fdopen(os.open("." + path, flags, *mode),
                              flag2mode(flags))
        self.fd = self.file.fileno()

    def read(self, length, offset):
        self.file.seek(offset)
        return self.file.read(length)

    def write(self, buf, offset):
        self.file.seek(offset)
        self.file.write(buf)
        return len(buf)

    def release(self, flags):
        self.file.close()

    def _fflush(self):
        if 'w' in self.file.mode or 'a' in self.file.mode:
            self.file.flush()

    def fsync(self, isfsyncfile):
        self._fflush()
        if isfsyncfile and hasattr(os, 'fdatasync'):
            os.fdatasync(self.fd)
        else:
            os.fsync(self.fd)

    def flush(self):
        self._fflush()
        # cf. xmp_flush() in fusexmp_fh.c
        os.close(os.dup(self.fd))

    def fgetattr(self):
        return os.fstat(self.fd)

    def ftruncate(self, len):
        self.file.truncate(len)

    def lock(self, cmd, owner, **kw):
        # The code here is much rather just a demonstration of the locking
        # API than something which actually was seen to be useful.

        # Advisory file locking is pretty messy in Unix, and the Python
        # interface to this doesn't make it better.
        # We can't do fcntl(2)/F_GETLK from Python in a platfrom independent
        # way. The following implementation *might* work under Linux.
        #
        # if cmd == fcntl.F_GETLK:
        #     import struct
        #
        #     lockdata = struct.pack('hhQQi', kw['l_type'], os.SEEK_SET,
        #                            kw['l_start'], kw['l_len'], kw['l_pid'])
        #     ld2 = fcntl.fcntl(self.fd, fcntl.F_GETLK, lockdata)
        #     flockfields = ('l_type', 'l_whence', 'l_start', 'l_len', 'l_pid')
        #     uld2 = struct.unpack('hhQQi', ld2)
        #     res = {}
        #     for i in xrange(len(uld2)):
        #          res[flockfields[i]] = uld2[i]
        #
        #     return fuse.Flock(**res)

        # Convert fcntl-ish lock parameters to Python's weird
        # lockf(3)/flock(2) medley locking API...
        op = {fcntl.F_UNLCK: fcntl.LOCK_UN,
              fcntl.F_RDLCK: fcntl.LOCK_SH,
              fcntl.F_WRLCK: fcntl.LOCK_EX}[kw['l_type']]
        if cmd == fcntl.F_GETLK:
            return -errno.EOPNOTSUPP
        elif cmd == fcntl.F_SETLK:
            if op != fcntl.LOCK_UN:
                op |= fcntl.LOCK_NB
        elif cmd == fcntl.F_SETLKW:
            pass
        else:
            return -errno.EINVAL

        fcntl.lockf(self.fd, op, kw['l_start'], kw['l_len'])


class PermissionCache:

    def __init__(self, uid_cache, host, timeout=30, size=1024):
        self._host = host
        self._timeout = timeout
        self._size = size
        self._data = {}
        self._entries = deque()
        self._lock = Lock()
        self._uid_cache = uid_cache

    def get(self, uid, path):
        try:
            entry, timestamp = self._data[uid, path]
            elapsed = time.time() - timestamp
            if elapsed > self._timeout:
                print('Timeout!', elapsed)
                uname = self._uid_cache.get(uid)
                entry = self._refresh_result(
                    uid, path, self._api_lookup(uname, path))
                return entry
            return entry
        except KeyError:
            pass
        uname = self._uid_cache.get(uid)
        try:
            entry = self._api_lookup(uname, path)
        except Exception:
            entry = 0
            log.exception('Error checking access for %s', path)
        self._save_result(uid, path, entry)
        return entry

    def _api_lookup(self, uname, path):
        if path.count('/') < 3:
            return os.R_OK
        path = self._mangle(path)
        url = (
            self._host
            + '/auth/repo_permissions?'
            + six.moves.urllib.parse.urlencode(dict(
                repo_path=path,
                username=uname)))
        print(f'Checking access for {uname} at {url} ({path})')
        fp = six.moves.urllib.request.urlopen(url)
        result = json.load(fp)
        print(result)
        entry = 0
        if result['allow_read']:
            entry |= os.R_OK
        if result['allow_write']:
            entry |= os.W_OK
        return entry

    def _refresh_result(self, uid, path, value):
        with self._lock:
            if (uid, path) in self._data:
                self._data[uid, path] = (value, time.time())
            else:
                if len(self._data) >= self._size:
                    k = self._entries.popleft()
                    del self._data[k]
                self._data[uid, path] = (value, time.time())
                self._entries.append((uid, path))
        return value

    def _save_result(self, uid, path, value):
        with self._lock:
            if len(self._data) >= self._size:
                k = self._entries.popleft()
                del self._data[k]
            self._data[uid, path] = (value, time.time())
            self._entries.append((uid, path))

    def _mangle(self, path):
        '''Convert paths from the form /SCM/neighborhood/project/a/b/c to
        /SCM/project.neighborhood/a/b/c
        '''
        parts = [p for p in path.split(os.path.sep) if p]
        scm, nbhd, proj, rest = parts[0], parts[1], parts[2], parts[3:]
        parts = [f'/SCM/{proj}.{nbhd}'] + rest
        return '/'.join(parts)


class UnixUsernameCache:

    def __init__(self):
        self._cache = {}

    def get(self, uid):
        try:
            return self._cache[uid]
        except KeyError:
            pass
        uname = pwd.getpwuid(uid).pw_name
        self._cache[uid] = uname
        return uname


def main():

    usage = """
Userspace nullfs-alike: mirror the filesystem tree from some point on.

""" + fuse.Fuse.fusage

    server = AccessFS(version="%prog " + fuse.__version__,
                      usage=usage,
                      dash_s_do='setsingle')

    server.parser.add_option(mountopt="root", metavar="PATH", default='/',
                             help="mirror filesystem from under PATH [default: %default]")
    server.parse(values=server, errex=1)

    try:
        if server.fuse_args.mount_expected():
            os.chdir(server.root)
    except OSError:
        print("can't enter root of underlying filesystem", file=sys.stderr)
        sys.exit(1)

    server.main()


if __name__ == '__main__':
    main()
