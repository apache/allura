#!/usr/bin/env python
import os
import sys
import pwd
import grp

def main():
    command = sys.argv[1]
    uname = sys.argv[2]
    eval(command)(uname, *sys.argv[3:])

def init(uname):
    home = os.path.join('/home', uname)
    ssh = os.path.join(home, '.ssh')
    os.mkdir(home)
    os.mkdir(ssh)
    u = pwd.getpwnam(uname)
    g = grp.getgrnam('scm')
    os.chmod(home, 0700)
    os.chmod(ssh, 0700)
    os.chown(home, u.pw_uid, g.gr_gid)
    os.chown(ssh, u.pw_uid, g.gr_gid)

def upload(uname, pubkey):
    keyfile = os.path.join('/home', uname, '.ssh', 'authorized_keys')
    u = pwd.getpwnam(uname)
    g = grp.getgrnam('scm')
    with open(keyfile, 'w') as fp:
        fp.write(pubkey)
    os.chown(keyfile, u.pw_uid, g.gr_gid)
    os.chmod(keyfile, 0600)

if __name__ == '__main__':
    main()
