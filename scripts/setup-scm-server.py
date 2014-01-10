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
import string
from tempfile import mkstemp
from ConfigParser import ConfigParser, NoOptionError

config = ConfigParser()


def main():
    config.read('.setup-scm-cache')
    if not config.has_section('scm'):
        config.add_section('scm')
    domain = get_value('domain', 'dc=example,dc=com')
    if config.get('start slapd', 'y') == 'y':
        run('service slapd start')
    if config.get('add base ldap schemas', 'y') == 'y':
        run('ldapadd -Y EXTERNAL -H ldapi:/// -f /etc/ldap/schema/cosine.ldif')
        run('ldapadd -Y EXTERNAL -H ldapi:/// -f /etc/ldap/schema/nis.ldif')
        run('ldapadd -Y EXTERNAL -H ldapi:/// -f /etc/ldap/schema/inetorgperson.ldif')
    secret = config.get('admin password', 'secret')
    if config.get('add backend ldif', 'y') == 'y':
        add_ldif(backend_ldif, domain=domain, secret=secret)
    if config.get('add frontend ldif', 'y') == 'y':
        add_ldif(frontend_ldif, domain=domain, secret=secret)


def get_value(key, default):
    try:
        value = config.get('scm', key)
    except NoOptionError:
        value = raw_input('%s? [%s]' % key, default)
        if not value:
            value = default
        config.set('scm', key, value)
    return value


def run(command):
    rc = os.system(command)
    assert rc == 0
    return rc


def add_ldif(template, **values):
    fd, name = mkstemp()
    os.write(fd, template.substitute(values))
    os.close(fd)
    run('ldapadd -Y EXTERNAL -H ldapi:/// -f %s' % name)
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
olcSuffix: $domain
olcDbDirectory: /var/lib/ldap
olcRootDN: cn=admin,$domain
olcRootPW: $secret
olcDbConfig: set_cachesize 0 2097152 0
olcDbConfig: set_lk_max_objects 1500
olcDbConfig: set_lk_max_locks 1500
olcDbConfig: set_lk_max_lockers 1500
olcDbIndex: objectClass eq
olcLastMod: TRUE
olcDbCheckpoint: 512 30
olcAccess: to attrs=userPassword by dn="cn=admin,$domain" write by anonymous auth by self write by * none
olcAccess: to attrs=shadowLastChange by self write by * read
olcAccess: to dn.base="" by * read
olcAccess: to * by dn="cn=admin,$domain" write by * read

''')

frontend_ldif = string.Template('''
# Create top-level object in domain
dn: $domain
objectClass: top
objectClass: dcObject
objectclass: organization
o: SCM Host Organization
dc: SCM
description: SCM Host Server

# Admin user.
dn: cn=admin,$domain
objectClass: simpleSecurityObject
objectClass: organizationalRole
cn: admin
description: LDAP administrator
userPassword: $secret

dn: ou=people,$domain
objectClass: organizationalUnit
ou: people

dn: ou=groups,$domain
objectClass: organizationalUnit
ou: groups
''')

if __name__ == '__main__':
    main()
