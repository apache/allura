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

import re
import os
import shutil
import string
import logging
import subprocess
import time
import operator as op
from subprocess import Popen, PIPE
from hashlib import sha1
from io import BytesIO
from datetime import datetime
import tempfile
from shutil import rmtree
import typing

import six
import tg
import pysvn
from paste.deploy.converters import asbool, asint
from pymongo.errors import DuplicateKeyError
from tg import tmpl_context as c, app_globals as g

from ming.base import Object
from ming.orm import Mapper, FieldProperty
from ming.utils import LazyProperty

from allura import model as M
from allura.lib import helpers as h
from allura.model.auth import User
from allura.model.repository import zipdir
from allura.model import repository as RM

if typing.TYPE_CHECKING:
    from ming.odm.mapper import Query


log = logging.getLogger(__name__)


class Repository(M.Repository):
    tool_name = 'SVN'
    repo_id = 'svn'
    type_s = 'SVN Repository'

    class __mongometa__:
        name = 'svn-repository'

    query: 'Query[Repository]'

    branches = FieldProperty([dict(name=str, object_id=str)])
    _refresh_precompute = False

    @LazyProperty
    def _impl(self):
        return SVNImplementation(self)

    def latest(self, branch=None):
        if self._impl is None:
            return None
        return self._impl.commit('HEAD')

    def tarball_filename(self, revision, path=None):
        fn = super().tarball_filename('r'+revision, path)
        path = self._impl._tarball_path_clean(path, revision)
        fn += ('-' + '-'.join(path.split('/'))) if path else ''
        return fn

    def rev_to_commit_id(self, rev):
        return self._impl.rev_parse(rev)


class SVNCalledProcessError(Exception):

    def __init__(self, cmd, returncode, stdout, stderr):
        self.cmd = cmd
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def __str__(self):
        return "Command: '%s' returned non-zero exit status %s\nSTDOUT: %s\nSTDERR: %s" % \
            (self.cmd, self.returncode, self.stdout, self.stderr)


def svn_path_exists(path, rev=None):
    svn = SVNLibWrapper(pysvn.Client())
    if rev:
        rev = pysvn.Revision(pysvn.opt_revision_kind.number, rev)
    else:
        rev = pysvn.Revision(pysvn.opt_revision_kind.head)
    try:
        svn.info2(path, revision=rev, recurse=False)
        return True
    except pysvn.ClientError:
        return False


class SVNLibWrapper:

    """Wrapper around pysvn, used for instrumentation."""

    def __init__(self, client):
        self.client = client

    def checkout(self, *args, **kw):
        return self.client.checkout(*args, **kw)

    def add(self, *args, **kw):
        return self.client.add(*args, **kw)

    def checkin(self, *args, **kw):
        return self.client.checkin(*args, **kw)

    def info2(self, *args, **kw):
        return self.client.info2(*args, **kw)

    def log(self, *args, **kw):
        return self.client.log(*args, **kw)

    def cat(self, *args, **kw):
        return self.client.cat(*args, **kw)

    def list(self, *args, **kw):
        return self.client.list(*args, **kw)

    def __getattr__(self, name):
        return getattr(self.client, name)


class SVNImplementation(M.RepositoryImplementation):
    post_receive_template = string.Template(
        '#!/bin/bash\n'
        '# The following is required for site integration, do not remove/modify.\n'
        '# Place user hook code in post-commit-user and it will be called from here.\n'
        'curl -s $url\n'
        '\n'
        'DIR="$$(dirname "$${BASH_SOURCE[0]}")"\n'
        'if [ -x $$DIR/post-commit-user ]; then'
        '  exec $$DIR/post-commit-user "$$@"\n'
        'fi')

    def __init__(self, repo):
        self._repo = repo

    @LazyProperty
    def _svn(self):
        return SVNLibWrapper(pysvn.Client())

    @LazyProperty
    def _url(self):
        return f'file://{self._repo.fs_path}{self._repo.name}'

    def shorthand_for_commit(self, oid):
        return '[r%d]' % self._revno(self.rev_parse(oid))

    def url_for_commit(self, commit, url_type=None):
        if hasattr(commit, '_id'):
            object_id = commit._id
        elif commit == self._repo.app.default_branch_name:
            object_id = commit
        else:
            object_id = self.rev_parse(commit)
        if ':' in object_id:
            object_id = str(self._revno(object_id))
        return os.path.join(self._repo.url(), object_id) + '/'

    def init(self, default_dirs=False, skip_special_files=False):
        fullname = self._setup_paths()
        log.info('svn init %s', fullname)
        if os.path.exists(fullname):
            shutil.rmtree(fullname)
        subprocess.call(['svnadmin', 'create', self._repo.name],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        cwd=self._repo.fs_path)
        if not skip_special_files:
            self._setup_special_files()
        self._repo.set_status('ready')
        # make first commit with dir structure
        if default_dirs:
            tmp_working_dir = tempfile.mkdtemp(prefix='allura-svn-r1-',
                                               dir=tg.config.get('scm.svn.tmpdir', g.tmpdir))
            log.info('tmp dir = %s', tmp_working_dir)
            self._repo._impl._svn.checkout(
                'file://' + fullname, tmp_working_dir)
            os.mkdir(tmp_working_dir + '/trunk')
            os.mkdir(tmp_working_dir + '/tags')
            os.mkdir(tmp_working_dir + '/branches')
            self._repo._impl._svn.add(tmp_working_dir + '/trunk')
            self._repo._impl._svn.add(tmp_working_dir + '/tags')
            self._repo._impl._svn.add(tmp_working_dir + '/branches')
            self._repo._impl._svn.checkin([tmp_working_dir + '/trunk',
                                           tmp_working_dir + '/tags',
                                           tmp_working_dir + '/branches'],
                                          'Initial commit')
            shutil.rmtree(tmp_working_dir)
            log.info('deleted %s', tmp_working_dir)

    def can_hotcopy(self, source_url):
        if not (asbool(tg.config.get('scm.svn.hotcopy', True)) and
                source_url.startswith('file://')):
            return False
        # check for svn version 1.7 or later
        stdout, stderr, returncode = self.check_call(['svn', '--version'])
        pattern = r'version (?P<maj>\d+)\.(?P<min>\d+)'
        m = re.search(pattern, six.ensure_text(stdout))
        return m and (int(m.group('maj')) * 10 + int(m.group('min'))) >= 17

    def check_call(self, cmd, fail_on_error=True):
        p = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE)
        stdout, stderr = p.communicate(input=b'p\n')
        if p.returncode != 0 and fail_on_error:
            self._repo.set_status('ready')
            raise SVNCalledProcessError(cmd, p.returncode, stdout, stderr)
        return stdout, stderr, p.returncode

    def clone_from(self, source_url):
        '''Initialize a repo as a clone of another using svnsync'''
        self.init(skip_special_files=True)

        def set_hook(hook_name):
            fn = os.path.join(self._repo.fs_path, self._repo.name,
                              'hooks', hook_name)
            with open(fn, 'w') as fp:
                fp.write('#!/bin/sh\n')
            os.chmod(fn, 0o755)

        def clear_hook(hook_name):
            fn = os.path.join(self._repo.fs_path, self._repo.name,
                              'hooks', hook_name)
            os.remove(fn)

        self._repo.set_status('importing')
        log.info('Initialize %r as a clone of %s',
                 self._repo, source_url)

        if self.can_hotcopy(source_url):
            log.info('... cloning %s via hotcopy', source_url)
            # src repo is on the local filesystem - use hotcopy (faster)
            source_path, dest_path = source_url[7:], self._url[7:]
            fullname = os.path.join(self._repo.fs_path, self._repo.name)
            # hotcopy expects dest dir to not exist yet
            if os.path.exists(fullname):
                shutil.rmtree(fullname)
            self.check_call(['svnadmin', 'hotcopy', source_path, dest_path])
            # make sure new repo has a pre-revprop-change hook,
            # otherwise the sync will fail
            set_hook('pre-revprop-change')
            self.check_call(
                ['svnsync', '--non-interactive', '--allow-non-empty',
                 'initialize', self._url, source_url])
            clear_hook('pre-revprop-change')
        else:
            def retry_cmd(cmd, fail_count=0):
                max_fail = asint(tg.config.get('scm.import.retry_count', 3))
                returncode = -1
                while returncode != 0 and fail_count < max_fail:
                    stdout, stderr, returncode = self.check_call(cmd, fail_on_error=False)
                    if returncode != 0:
                        fail_count += 1
                        log.info('Attempt %s.  Error running %s Details:\n%s', fail_count, cmd, stderr)
                        time.sleep(asint(tg.config.get('scm.import.retry_sleep_secs', 5)))
                    if fail_count == max_fail:
                        raise SVNCalledProcessError(cmd, returncode, stdout, stderr)
                return fail_count
            set_hook('pre-revprop-change')
            fail_count = retry_cmd(['svnsync', 'init', self._url, source_url])
            fail_count = retry_cmd(['svnsync', '--non-interactive', 'sync', self._url], fail_count=fail_count)
            clear_hook('pre-revprop-change')

        log.info('... %r cloned', self._repo)
        self.update_checkout_url()
        self._setup_special_files(source_url)

    def update_checkout_url(self):
        """Validate the current ``checkout_url`` against the on-disk repo,
        and change it if necessary.

        If ``checkout_url`` is valid and not '', no changes are made.
        If ``checkout_url`` is invalid or '':

            - Set it to 'trunk' if repo has a top-level trunk directory
            - Else, set it to ''

        """
        opts = self._repo.app.config.options
        if not svn_path_exists('file://{}{}/{}'.format(self._repo.fs_path,
                                                          self._repo.name, opts['checkout_url'])):
            opts['checkout_url'] = ''

        if (not opts['checkout_url'] and
                svn_path_exists(
                    'file://{}{}/trunk'.format(self._repo.fs_path,
                                                 self._repo.name))):
            opts['checkout_url'] = 'trunk'

    def commit(self, rev):
        oid = self.rev_parse(rev)
        result = M.repository.Commit.query.get(_id=oid)
        if result:
            result.set_context(self._repo)
        return result

    def rev_parse(self, rev):
        if rev in ('HEAD', None):
            return self._oid(self.head)
        elif isinstance(rev, int) or rev.isdigit():
            return self._oid(rev)
        else:
            return rev

    def all_commit_ids(self):
        """Return a list of commit ids, starting with the head (most recent
        commit) and ending with the root (first commit).
        """
        head_revno = self.head
        return list(map(self._oid, list(range(head_revno, 0, -1))))

    def new_commits(self, all_commits=False):
        head_revno = self.head
        oids = [self._oid(revno) for revno in range(1, head_revno + 1)]
        if all_commits:
            return oids
        # Find max commit id -- everything greater than that will be "unknown"
        prefix = self._oid('')
        q = M.repository.Commit.query.find(
            dict(
                type='commit',
                _id={'$gt': prefix},
            ),
            dict(_id=True)
        )
        seen_oids = set()
        for d in q.ming_cursor.cursor:
            oid = d['_id']
            if not oid.startswith(prefix):
                break
            seen_oids.add(oid)
        return [o for o in oids if o not in seen_oids]

    def refresh_commit_info(self, oid, seen_object_ids, lazy=True):
        from allura.model.repository import CommitDoc
        ci_doc = CommitDoc.m.get(_id=oid)
        if ci_doc and lazy:
            return False
        revno = self._revno(oid)
        rev = self._revision(oid)
        try:
            log_entry = self._svn.log(
                self._url,
                revision_start=rev,
                limit=1,
                discover_changed_paths=True)[0]
        except pysvn.ClientError:
            log.info('ClientError processing %r %r, treating as empty',
                     oid, self._repo, exc_info=True)
            log_entry = Object(date='', message='', changed_paths=[])
        log_date = None
        if hasattr(log_entry, 'date'):
            log_date = datetime.utcfromtimestamp(log_entry.date)
        user = Object(
            name=h.really_unicode(log_entry.get('author', '--none--')),
            email='',
            date=log_date)
        args = dict(
            tree_id=None,
            committed=user,
            authored=user,
            message=h.really_unicode(log_entry.get("message", "--none--")),
            parent_ids=[],
            child_ids=[])
        if revno > 1:
            args['parent_ids'] = [self._oid(revno - 1)]
        if ci_doc:
            ci_doc.update(**args)
            ci_doc.m.save()
        else:
            ci_doc = CommitDoc(dict(args, _id=oid))
            try:
                ci_doc.m.insert()
            except DuplicateKeyError:
                if lazy:
                    return False
        return True

    def compute_tree_new(self, commit, tree_path='/'):
        # always leading slash, never trailing
        tree_path = '/' + tree_path.strip('/')
        tree_id = self._tree_oid(commit._id, tree_path)
        tree = RM.Tree.query.get(_id=tree_id)
        if tree:
            return tree_id
        log.debug('Computing tree for %s: %s',
                  self._revno(commit._id), tree_path)
        rev = self._revision(commit._id)
        try:
            infos = self._svn.info2(
                self._url + tree_path,
                revision=rev,
                depth=pysvn.depth.immediates)
        except pysvn.ClientError:
            log.exception('Error computing tree for: %s: %s(%s)',
                          self._repo, commit, tree_path)
            return None
        log.debug('Compute tree for %d paths', len(infos))
        tree_ids = []
        blob_ids = []
        lcd_entries = []
        for path, info in infos[1:]:
            if info.kind == pysvn.node_kind.dir:
                tree_ids.append(Object(
                    id=self._tree_oid(commit._id, path),
                    name=path))
            elif info.kind == pysvn.node_kind.file:
                blob_ids.append(Object(
                    id=self._tree_oid(commit._id, path),
                    name=path))
            else:
                raise AssertionError()
            lcd_entries.append(dict(
                name=path,
                commit_id=self._oid(info.last_changed_rev.number),
            ))
        tree, is_new = RM.Tree.upsert(tree_id,
                                      tree_ids=tree_ids,
                                      blob_ids=blob_ids,
                                      other_ids=[],
                                      )
        if is_new:
            commit_id = self._oid(infos[0][1].last_changed_rev.number)
            path = tree_path.strip('/')
            RM.LastCommitDoc.m.update_partial(
                {'commit_id': commit_id, 'path': path},
                {'commit_id': commit_id, 'path':
                 path, 'entries': lcd_entries},
                upsert=True)
        return tree_id

    def _tree_oid(self, commit_id, path):
        data = f'tree\n{commit_id}\n{h.really_unicode(path)}'
        return sha1(data.encode('utf-8')).hexdigest()

    def _blob_oid(self, commit_id, path):
        data = f'blob\n{commit_id}\n{h.really_unicode(path)}'
        return sha1(data.encode('utf-8')).hexdigest()

    def _obj_oid(self, commit_id, info):
        path = info.URL[len(info.repos_root_URL):]
        if info.kind == pysvn.node_kind.dir:
            return self._tree_oid(commit_id, path)
        else:
            return self._blob_oid(commit_id, path)

    def log(self, revs=None, path=None, exclude=None, id_only=True, limit=25, **kw):
        """
        Returns a generator that returns information about commits reachable
        by revs.

        revs can be None or a list or tuple of identifiers, each of which
        can be anything parsable by self.commit().  If revs is None, the
        default head will be used.

        If path is not None, only commits which modify files under path
        will be included.

        Exclude can be None or a list or tuple of identifiers, each of which
        can be anything parsable by self.commit().  If not None, then any
        revisions reachable by any of the revisions in exclude will not be
        included.

        If id_only is True, returns only the commit ID, otherwise it returns
        detailed information about each commit.

        Since pysvn doesn't have a generator version of log, this tries to
        balance pulling too much data from SVN with calling SVN too many
        times by pulling in pages of page_size at a time.
        """
        if revs is None:
            revno = self.head
        else:
            revno = max(self._revno(self.rev_parse(r)) for r in revs)
        if exclude is None:
            exclude = 0
        else:
            exclude = max(self._revno(self.rev_parse(r)) for r in exclude)
        if path is None:
            url = self._url
        else:
            url = '/'.join([self._url, path.strip('/')])
        while revno > exclude:
            rev = pysvn.Revision(pysvn.opt_revision_kind.number, revno)
            try:
                logs = self._svn.log(
                    url, revision_start=rev, peg_revision=rev, limit=limit,
                    discover_changed_paths=True)
            except pysvn.ClientError as e:
                if 'Unable to connect' in e.args[0]:
                    raise  # repo error
                return  # no (more) history for this path
            for ci in logs:

                if ci.revision.number <= exclude:
                    return
                if id_only:
                    yield ci.revision.number
                else:
                    yield self._map_log(ci, url, path)
            if len(logs) < limit:
                # we didn't get a full page, don't bother calling SVN again
                return
            revno = ci.revision.number - 1

    def _check_changed_path(self, changed_path, path):
        if (changed_path['copyfrom_path'] and
                changed_path['path'] and
                path and
                (len(changed_path['path']) < len(path)) and
                path.startswith(changed_path['path'])):
                changed_path['copyfrom_path'] = changed_path['copyfrom_path'] + \
                    path[len(changed_path['path']):]
                changed_path['path'] = path
        return changed_path

    def _map_log(self, ci, url, path=None):
        revno = ci.revision.number
        rev = pysvn.Revision(pysvn.opt_revision_kind.number, revno)
        size = None
        if path:
            try:
                size = self._svn.list(url, revision=rev, peg_revision=rev)[0][0].size
            except pysvn.ClientError:
                pass
        rename_details = {}
        changed_paths = ci.get('changed_paths', [])
        for changed_path in changed_paths:
            changed_path = self._check_changed_path(changed_path, path)
            if changed_path['copyfrom_path'] and changed_path['path'] == path and changed_path['action'] == 'A':
                rename_details['path'] = changed_path['copyfrom_path']
                rename_details['commit_url'] = self._repo.url_for_commit(
                    changed_path['copyfrom_revision'].number
                )
                break
        return {
            'id': revno,
            'message': h.really_unicode(ci.get('message', '--none--')),
            'authored': {
                'name': h.really_unicode(ci.get('author', '--none--')),
                'email': '',
                'date': datetime.utcfromtimestamp(ci.date),
            },
            'committed': {
                'name': h.really_unicode(ci.get('author', '--none--')),
                'email': '',
                'date': datetime.utcfromtimestamp(ci.date),
            },
            'refs': ['HEAD'] if revno == self.head else [],
            'parents': [revno - 1] if revno > 1 else [],
            'size': size,
            'rename_details': rename_details,
        }

    def open_blob(self, blob):
        data = self._svn.cat(
            self._url + h.urlquote(blob.path()),
            revision=self._revision(blob.commit._id))
        return BytesIO(data)

    def blob_size(self, blob):
        try:
            rev = self._revision(blob.commit._id)
            data = self._svn.list(
                self._url + blob.path(),
                revision=rev,
                peg_revision=rev,
                dirent_fields=pysvn.SVN_DIRENT_SIZE)
        except pysvn.ClientError:
            log.info('ClientError getting filesize %r %r, returning 0',
                     blob.path(), self._repo, exc_info=True)
            return 0

        try:
            size = data[0][0]['size']
        except (IndexError, KeyError):
            log.info(
                'Error getting filesize: bad data from svn client %r %r, returning 0',
                blob.path(), self._repo, exc_info=True)
            size = 0

        return size

    def _setup_hooks(self, source_path=None):
        'Set up the post-commit and pre-revprop-change hooks'
        # setup a post-commit hook to notify Allura of changes to the repo
        # the hook should also call the user-defined post-commit-user hook
        text = self.post_receive_template.substitute(
            url=self._repo.refresh_url())
        fn = os.path.join(self._repo.fs_path, self._repo.name,
                          'hooks', 'post-commit')
        with open(fn, 'w') as fp:
            fp.write(text)
        os.chmod(fn, 0o755)

    def _revno(self, oid):
        return int(oid.split(':')[1])

    def _revision(self, oid):
        return pysvn.Revision(
            pysvn.opt_revision_kind.number,
            self._revno(oid))

    def _oid(self, revno):
        return f'{self._repo._id}:{revno}'

    def last_commit_ids(self, commit, paths):
        '''
        Return a mapping {path: commit_id} of the _id of the last
        commit to touch each path, starting from the given commit.

        Since SVN Diffs are computed on-demand, we can't walk the
        commit tree to find these.  However, we can ask SVN for it
        with a single call, so it shouldn't be too expensive.

        NB: This assumes that all paths are direct children of a
        single common parent path (i.e., you are only asking for
        a subset of the nodes of a single tree, one level deep).
        '''
        if len(paths) == 1:
            tree_path = '/' + os.path.dirname(paths[0].strip('/'))
        else:
            # always leading slash, never trailing
            tree_path = '/' + os.path.commonprefix(paths).strip('/')
        paths = [path.strip('/') for path in paths]
        rev = self._revision(commit._id)
        try:
            infos = self._svn.info2(
                self._url + tree_path,
                revision=rev,
                depth=pysvn.depth.immediates)
        except pysvn.ClientError:
            log.exception('Error computing tree for: %s: %s(%s)',
                          self._repo, commit, tree_path)
            return None
        entries = {}
        for path, info in infos[1:]:
            path = os.path.join(tree_path, path).strip('/')
            if path in paths:
                entries[path] = self._oid(info.last_changed_rev.number)
        return entries

    def get_changes(self, oid):
        rev = self._revision(oid)
        try:
            log_entry = self._svn.log(
                self._url,
                revision_start=rev,
                limit=1,
                discover_changed_paths=True)[0]
        except pysvn.ClientError:
            log.info('ClientError processing %r %r, treating as empty',
                     oid, self._repo, exc_info=True)
            log_entry = Object(date='', message='', changed_paths=[])
        return [p.path for p in log_entry.changed_paths]

    def _tarball_path_clean(self, path, rev=None):
        if path:
            return path.strip('/')
        else:
            trunk_exists = svn_path_exists('file://{}{}/{}'.format(self._repo.fs_path, self._repo.name, 'trunk'), rev)
            if trunk_exists:
                return 'trunk'
            return ''

    def tarball(self, commit, path=None):
        """
        Makes a svn export at `tmpdest`
            then zips that into `dest/tmpfilename`
            then renames that to `dest/filename`
        """
        path = self._tarball_path_clean(path, commit)
        if not os.path.exists(self._repo.tarball_path):
            os.makedirs(self._repo.tarball_path)
        if not os.path.exists(self._repo.tarball_tmpdir):
            os.makedirs(self._repo.tarball_tmpdir)
        archive_name = self._repo.tarball_filename(commit, path)
        dest = os.path.join(self._repo.tarball_path, archive_name)
        tmpdest = os.path.join(self._repo.tarball_tmpdir, archive_name)
        filename = os.path.join(self._repo.tarball_path, '{}{}'.format(archive_name, '.zip')).encode('utf-8')
        tmpfilename = os.path.join(self._repo.tarball_path, '{}{}'.format(archive_name, '.tmp')).encode('utf-8')
        rmtree(dest.encode('utf8'), ignore_errors=True)  # must encode into bytes or it'll fail on non-ascii filenames
        rmtree(tmpdest.encode('utf8'), ignore_errors=True)
        path = os.path.join(self._url, path)
        try:
            # need to set system locale to handle all symbols in filename
            import locale
            locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
            self._svn.export(path,
                             tmpdest,
                             revision=pysvn.Revision(
                                 pysvn.opt_revision_kind.number, commit),
                             ignore_externals=True)
            zipdir(tmpdest, tmpfilename)
            os.rename(tmpfilename, filename)
        finally:
            rmtree(dest.encode('utf8'), ignore_errors=True)
            rmtree(tmpdest.encode('utf8'), ignore_errors=True)
            if os.path.exists(tmpfilename):
                os.remove(tmpfilename)

    def is_empty(self):
        return self.head == 0

    def is_file(self, path, rev=None):
        url = '/'.join([self._url, path.strip('/')])
        rev = pysvn.Revision(pysvn.opt_revision_kind.number,
                             self._revno(self.rev_parse(rev)))
        try:
            info = self._svn.list(
                url, revision=rev, peg_revision=rev, dirent_fields=pysvn.SVN_DIRENT_KIND)[0][0]
            return info.kind == pysvn.node_kind.file
        except pysvn.ClientError:
            return False

    def symbolics_for_commit(self, commit):
        return [], []

    @LazyProperty
    def head(self):
        try:
            return int(self._svn.revpropget('revision', url=self._url)[0].number)
        except pysvn.ClientError as e:
            error_lines = str(e).splitlines()
            if all(errline.startswith(("Unable to connect", "Unable to open")) for errline in error_lines):
                # simple common error e.g. empty repo directory
                return 0
            else:
                raise

    @LazyProperty
    def heads(self):
        return [Object(name=None, object_id=self._oid(self.head))]

    @LazyProperty
    def branches(self):
        return []

    @LazyProperty
    def tags(self):
        return []

    def paged_diffs(self, commit_id, start=0, end=None, onlyChangedFiles=False):
        result = {'added': [], 'removed': [], 'changed': [], 'copied': [], 'renamed': [], 'total': 0}
        rev = self._revision(commit_id)
        try:
            log_info = self._svn.log(
                self._url,
                revision_start=rev,
                revision_end=rev,
                discover_changed_paths=True)
        except pysvn.ClientError:
            log.info('Error getting paged_diffs log of %s on %s',
                     commit_id, self._url, exc_info=True)
            return result
        if len(log_info) == 0:
            return result
        paths = sorted(log_info[0].changed_paths, key=op.itemgetter('path'))
        result['total'] = len(paths)
        for p in paths[start:end]:
            if p['copyfrom_path'] is not None:
                result['copied'].append({
                    'new': h.really_unicode(p.path),
                    'old': h.really_unicode(p.copyfrom_path),
                    'ratio': 1,
                })
            elif p['action'] == 'A':
                result['added'].append(h.really_unicode(p.path))
            elif p['action'] == 'D':
                result['removed'].append(h.really_unicode(p.path))
            elif p['action'] in ['M', 'R']:
                # 'R' means 'Replaced', i.e.
                # svn rm aaa.txt
                # echo "Completely new aaa!" > aaa.txt
                # svn add aaa.txt
                # svn commit -m "Replace aaa.txt"
                result['changed'].append(h.really_unicode(p.path))

        for r in result['copied'][:]:
            if r['old'] in result['removed']:
                result['removed'].remove(r['old'])
                result['copied'].remove(r)
                result['renamed'].append(r)
            if r['new'] in result['added']:
                result['added'].remove(r['new'])

        return result

Mapper.compile_all()
