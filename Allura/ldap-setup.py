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
import shutil
import string
import logging
from contextlib import contextmanager
from tempfile import mkstemp
from six.moves.configparser import ConfigParser, NoOptionError

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger('ldap-setup')

config = ConfigParser()


def main():
    config.read('.setup-scm-cache')
    if not config.has_section('scm'):
        config.add_section('scm')
    suffix = get_value('suffix', 'dc=localdomain')
    secret = get_value('admin password', 'secret')
    firstdc = suffix.split(',')[0].split('=')[1]
    if get_value('clear ldap config', 'y') == 'y':
        run('apt-get -f install')
        run('apt-get remove --purge slapd ldap-utils')
        run('apt-get install slapd ldap-utils')
    if get_value('start slapd', 'y') == 'y':
        run('service slapd start')
    if get_value('add base ldap schemas', 'y') == 'y':
        run('ldapadd -Y EXTERNAL -H ldapi:/// -f /etc/ldap/schema/cosine.ldif')
        run('ldapadd -Y EXTERNAL -H ldapi:/// -f /etc/ldap/schema/nis.ldif')
        run('ldapadd -Y EXTERNAL -H ldapi:/// -f /etc/ldap/schema/inetorgperson.ldif')
    if get_value('add backend ldif', 'y') == 'y':
        with tempfile(backend_ldif, locals()) as name:
            run('ldapadd -Y EXTERNAL -H ldapi:/// -f %s' % name)
    with open('/etc/ldap.secret', 'w') as fp:
        fp.write(secret)
    os.chmod('/etc/ldap.secret', 0o400)
    if get_value('add frontend ldif', 'y') == 'y':
        with tempfile(frontend_ldif, locals()) as name:
            run('ldapadd -c -x -D cn=admin,%s -W -f %s -y /etc/ldap.secret' %
                (suffix, name))
    if get_value('add initial user/group', 'y') == 'y':
        with tempfile(initial_user_ldif, locals()) as name:
            run('ldapadd -c -x -D cn=admin,%s -W -f %s -y /etc/ldap.secret' %
                (suffix, name))
    if get_value('setup ldap auth', 'y') == 'y':
        run('apt-get install libnss-ldap')
        run('dpkg-reconfigure ldap-auth-config')
        run('auth-client-config -t nss -p lac_ldap')
        run('pam-auth-update')
    if get_value('setup ldapscripts', 'y') == 'y':
        run('apt-get install ldapscripts')
        with tempfile(ldapscripts_conf, locals()) as name:
            shutil.copy(name, '/etc/ldapscripts/ldapscripts.conf')
        log.info('writing passwd')
        with open('/etc/ldapscripts/ldapscripts.passwd', 'w') as fp:
            fp.write(secret)
        os.chmod('/etc/ldapscripts/ldapscripts.passwd', 0o400)
        log.info('writing runtime')
        with open('/usr/share/ldapscripts/runtime.debian', 'w') as fp:
            fp.write(ldapscripts_debian)


def get_value(key, default):
    try:
        default = config.get('scm', key)
    except NoOptionError:
        pass
    value = input(f'{key}? [{default}]')
    if not value:
        value = default
    config.set('scm', key, value)
    with open('.setup-scm-cache', 'w') as fp:
        config.write(fp)
    return value


def run(command):
    rc = os.system(command)
    if rc != 0:
        log.error('Error running %s', command)
    assert rc == 0
    return rc


@contextmanager
def tempfile(template, values):
    fd, name = mkstemp()
    os.write(fd, template.safe_substitute(values))
    os.close(fd)
    yield name
    os.remove(name)

backend_ldif = string.Template('''
# Load dynamic backend modules
dn: cn=module,cn=config
objectClass: olcModuleList
cn: module
olcModulepath: /usr/lib/ldap
olcModuleload: back_hdb

# Database settings
dn: olcDatabase=hdb,cn=config
objectClass: olcDatabaseConfig
objectClass: olcHdbConfig
olcDatabase: {1}hdb
olcSuffix: $suffix
olcDbDirectory: /var/lib/ldap
olcRootDN: cn=admin,$suffix
olcRootPW: $secret
olcDbConfig: set_cachesize 0 2097152 0
olcDbConfig: set_lk_max_objects 1500
olcDbConfig: set_lk_max_locks 1500
olcDbConfig: set_lk_max_lockers 1500
olcDbIndex: objectClass eq
olcLastMod: TRUE
olcDbCheckpoint: 512 30
olcAccess: to attrs=userPassword by dn="cn=admin,$suffix" write by anonymous auth by self write by * none
olcAccess: to attrs=shadowLastChange by self write by * read
olcAccess: to dn.base="" by * read
olcAccess: to * by dn="cn=admin,$suffix" write by * read

''')

frontend_ldif = string.Template('''
# Create top-level object in domain
dn: $suffix
objectClass: top
objectClass: dcObject
objectclass: organization
o: Example Organization
dc: $firstdc
description: LDAP Example

# Create max uid generator
dn: cn=maxUid,$suffix
objectClass: extensibleObject
objectClass: top
uidNumber: 10000

# Admin user.
dn: cn=admin,$suffix
objectClass: simpleSecurityObject
objectClass: organizationalRole
cn: admin
description: LDAP administrator
userPassword: $secret

dn: ou=people,$suffix
objectClass: organizationalUnit
ou: people

dn: ou=groups,$suffix
objectClass: organizationalUnit
ou: groups
''')

initial_user_ldif = string.Template('''
dn: uid=john,ou=people,$suffix
objectClass: inetOrgPerson
objectClass: posixAccount
objectClass: shadowAccount
uid: john
sn: Doe
givenName: John
cn: John Doe
displayName: John Doe
uidNumber: 1000
gidNumber: 10000
userPassword: password
gecos: John Doe
loginShell: /bin/bash
homeDirectory: /home/john
shadowExpire: -1
shadowFlag: 0
shadowWarning: 7
shadowMin: 8
shadowMax: 999999
shadowLastChange: 10877
mail: john.doe@example.com
postalCode: 31000
l: Toulouse
o: Example
mobile: +33 (0)6 xx xx xx xx
homePhone: +33 (0)5 xx xx xx xx
title: System Administrator
postalAddress:
initials: JD

dn: cn=example,ou=groups,$suffix
objectClass: posixGroup
cn: example
gidNumber: 10000
''')

open_ldap_config = string.Template('''
[open_ldap]
nss_passwd=passwd: files ldap
nss_group=group: files ldap
nss_shadow=shadow: files ldap
nss_netgroup=netgroup: files ldap
pam_auth=auth       required     pam_env.so
        auth       sufficient   pam_unix.so likeauth nullok
#the following line (containing pam_group.so) must be placed before pam_ldap.so
#for ldap users to be placed in local groups such as fuse, plugdev, scanner, etc ...
        auth       required     pam_group.so use_first_pass
        auth       sufficient   pam_ldap.so use_first_pass
        auth       required     pam_deny.so
pam_account=account    sufficient   pam_unix.so
        account    sufficient   pam_ldap.so
        account    required     pam_deny.so
pam_password=password   sufficient   pam_unix.so nullok md5 shadow
        password   sufficient   pam_ldap.so use_first_pass
        password   required     pam_deny.so
pam_session=session    required     pam_limits.so
        session    required     pam_mkhomedir.so skel=/etc/skel/
        session    required     pam_unix.so
        session    optional     pam_ldap.so
''')

ldapscripts_conf = string.Template('''
SERVER=127.0.0.1
BINDDN='cn=admin,$suffix'
BINDPWDFILE="/etc/ldapscripts/ldapscripts.passwd"
SUFFIX='$suffix'
GSUFFIX='ou=Groups'
USUFFIX='ou=People'
MSUFFIX='ou=Computers'
GIDSTART=10000
UIDSTART=10000
MIDSTART=10000
''')


ldapscripts_debian = r'''
### Allura-customized
### This file predefine some ldapscripts variables for Debian boxes.
#
#  Copyright (c) 2005 Ganal LAPLANCHE - Linagora
#  Copyright (c) 2005-2007 Pierre Habouzit
#  Copyright (c) 2009 Alexander GQ Gerasiov
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307,
#  USA.

##### Beginning of ldapscripts configuration #####

getfield() {
    local field="$1"
    local nssconffile='/etc/libnss-ldap.conf'
    if [ -f "$nssconffile" ];then
        local value=$(awk "/^\s*$field/ {print \$2}" /etc/libnss-ldap.conf)
    else
        local value="$2"
    fi
    echo ${value:-$2}
}

getsuffix() {
    field="$1"
    value="$(getfield "$1" | sed -e "s/,.*$//")"
    echo ${value:-$2}
}

# LDAP Configuration
SERVER=$(getfield uri "$(getfield host '')")
BINDDN=$(getfield rootbinddn '')
if [ -f /etc/libnss-ldap.secret ];then
        BINDPWDFILE=/etc/libnss-ldap.secret
elif [ -f /etc/ldap.secret ];then
        BINDPWDFILE=/etc/ldap.secret
fi

SUFFIX=`getfield base`
GSUFFIX=`getsuffix nss_base_group   'ou=Group'`
USUFFIX=`getsuffix nss_base_passwd  'ou=People'`
MSUFFIX=`getsuffix nss_base_hosts   'ou=Hosts'`

# User properties
[ -f /etc/adduser.conf ] && . /etc/adduser.conf
USHELL=${DSHELL:-"/bin/bash"}
UHOMES=${DHOME:-"/home"}"/%u"
HOMESKEL=${SKEL:-"/etc/skel"}
HOMEPERMS=${DIR_MODE:-"0755"}


# Where to log
LOGFILE="/var/log/ldapscripts.log"

# Various binaries used within scripts
LDAPSEARCHBIN=`which ldapsearch`
LDAPADDBIN=`which ldapadd`
LDAPDELETEBIN=`which ldapdelete`
LDAPMODIFYBIN=`which ldapmodify`
LDAPMODRDNBIN=`which ldapmodrdn`
LDAPPASSWDBIN=`which ldappasswd`

# Getent command to use - choose the ones used on your system. Leave blank or comment for auto-guess.
# GNU/Linux
GETENTPWCMD="getent passwd"
GETENTGRCMD="getent group"


TMPDIR="/tmp"
##### End of configuration #####
'''
if __name__ == '__main__':
    main()
