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

import sys
import logging
from collections import OrderedDict

from pylons import tmpl_context as c
from ming.orm import session
from bson import ObjectId

from allura import model as M
from allura.lib import utils
from forgewiki.wiki_main import ForgeWikiApp

log = logging.getLogger('fix-home-permissions')
handler = logging.StreamHandler(sys.stdout)
log.addHandler(handler)

TEST = sys.argv[-1].lower() == 'test'


def main():

    if TEST:
        log.info('Examining permissions for all Home Wikis')
    else:
        log.info('Fixing permissions for all Home Wikis')

    for some_projects in utils.chunked_find(M.Project, {'neighborhood_id': {
        '$nin': [ObjectId('4be2faf8898e33156f00003e'),      # /u
                 ObjectId('4dbf2563bfc09e6362000005')]}}):  # /motorola
        for project in some_projects:
            c.project = project
            home_app = project.app_instance('home')
            if isinstance(home_app, ForgeWikiApp):
                log.info('Examining permissions in project "%s".' %
                         project.shortname)
                root_project = project.root_project or project
                authenticated_role = project_role(
                    root_project, '*authenticated')
                member_role = project_role(root_project, 'Member')

                # remove *authenticated create/update permissions
                new_acl = OrderedDict(
                    ((ace.role_id, ace.access, ace.permission), ace)
                    for ace in home_app.acl
                    if not (
                        ace.role_id == authenticated_role._id and ace.access == M.ACE.ALLOW and ace.permission in (
                            'create', 'edit', 'delete', 'unmoderated_post')
                    )
                )
                if (member_role._id, M.ACE.ALLOW, 'update') in new_acl:
                    del new_acl[(member_role._id, M.ACE.ALLOW, 'update')]

                # add member create/edit permissions
                new_acl[(member_role._id, M.ACE.ALLOW, 'create')
                        ] = M.ACE.allow(member_role._id, 'create')
                new_acl[(member_role._id, M.ACE.ALLOW, 'edit')
                        ] = M.ACE.allow(member_role._id, 'edit')
                new_acl[(member_role._id, M.ACE.ALLOW, 'unmoderated_post')] = M.ACE.allow(
                    member_role._id, 'unmoderated_post')

                if TEST:
                    log.info(
                        '...would update acl for home app in project "%s".' %
                        project.shortname)
                else:
                    log.info('...updating acl for home app in project "%s".' %
                             project.shortname)
                    home_app.config.acl = map(dict, new_acl.values())
                    session(home_app.config).flush()


def project_role(project, name):
    role = M.ProjectRole.query.get(project_id=project._id, name=name)
    if role is None:
        role = M.ProjectRole(project_id=project._id, name=name)
    return role

if __name__ == '__main__':
    main()
