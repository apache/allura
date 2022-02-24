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
    os.chmod(home, 0o700)
    os.chmod(ssh, 0o700)
    os.chown(home, u.pw_uid, g.gr_gid)
    os.chown(ssh, u.pw_uid, g.gr_gid)


def upload(uname, pubkey):
    keyfile = os.path.join('/home', uname, '.ssh', 'authorized_keys')
    u = pwd.getpwnam(uname)
    g = grp.getgrnam('scm')
    with open(keyfile, 'w') as fp:
        fp.write(pubkey)
    os.chown(keyfile, u.pw_uid, g.gr_gid)
    os.chmod(keyfile, 0o600)

if __name__ == '__main__':
    main()
