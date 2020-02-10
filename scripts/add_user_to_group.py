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

"""
Add a user to group on a project.

Especially useful for making admin1 a neighborhood admin after loading a
production dataset.

Example:
    # Add admin1 to Admin group for the entire /p/ neighborhood:
    $ paster script production.ini ../scripts/add_user_to_group.py -- admin1 Admin

    # Add admin1 to Member group on project /p/allura:
    $ paster script production.ini ../scripts/add_user_to_group.py -- admin1 Member allura

    # Add admin1 to Developer group on project /berlios/codeblocks:
    $ paster script production.ini ../scripts/add_user_to_group.py -- admin1 Developer codeblocks --nbhd=/berlios/

    # Add admin1 to Admin group for entire berlios neighborhood:
    $ paster script production.ini ../scripts/add_user_to_group.py -- admin1 Admin --nbhd=/berlios/

"""

from __future__ import unicode_literals
from __future__ import absolute_import
from allura import model as M
from ming.orm import ThreadLocalORMSession


def main(options):
    nbhd = M.Neighborhood.query.get(url_prefix=options.nbhd)
    if not nbhd:
        return "Couldn't find neighborhood with url_prefix '%s'" % options.nbhd
    project = M.Project.query.get(neighborhood_id=nbhd._id,
                                  shortname=options.project)
    if not project:
        return "Couldn't find project with shortname '%s'" % options.project
    user = M.User.by_username(options.user)
    if not user:
        return "Couldn't find user with username '%s'" % options.user
    project_role = M.ProjectRole.by_name(options.group, project=project)
    if not project_role:
        return "Couldn't find group (ProjectRole) with name '%s'" % options.group
    user_roles = M.ProjectRole.by_user(
        user, project=project, upsert=True).roles
    if project_role._id not in user_roles:
        user_roles.append(project_role._id)
    ThreadLocalORMSession.flush_all()


def parse_options():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('user', help='Username')
    parser.add_argument('group', help='Group (ProjectRole) name, e.g. Admin, '
                        'Member, Developer, etc.')
    parser.add_argument('project', nargs='?', default='--init--',
                        help='Project shortname. Default is --init--.')
    parser.add_argument('--nbhd', default='/p/', help='Neighborhood '
                        'url_prefix. Default is /p/.')
    return parser.parse_args()


if __name__ == '__main__':
    import sys
    sys.exit(main(parse_options()))
