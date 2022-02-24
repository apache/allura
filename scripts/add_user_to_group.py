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

    # Replace admin1 with admin2 in all individual projects in berlios neighborhood:
    $ paster script production.ini ../scripts/add_user_to_group.py -- admin2 Admin ALLPROJECTS --nbhd=/berlios/ --replace-users admin1

"""


import logging

from allura import model as M
from allura.lib.utils import chunked_find
from allura.model import main_orm_session
from ming.orm import ThreadLocalORMSession


log = logging.getLogger(__name__)


def main(options):
    nbhd = M.Neighborhood.query.get(url_prefix=options.nbhd)
    if not nbhd:
        return "Couldn't find neighborhood with url_prefix '%s'" % options.nbhd

    user = M.User.by_username(options.user)
    if not user:
        return "Couldn't find user with username '%s'" % options.user

    replace_users = []
    for replace_username in options.replace_users:
        u = M.User.by_username(replace_username)
        if not u:
            return "Couldn't find user with username '%s'" % replace_username
        else:
            replace_users.append(u)

    if options.project == 'ALLPROJECTS':
        for chunk in chunked_find(M.Project, dict(
                neighborhood_id=nbhd._id,
                shortname={'$ne': '--init--'},
        )):
            for p in chunk:
                update_project(options, user, p, replace_users=replace_users)
                # clears User, Project, ProjectRole... so they're not taking up memory and making flush_all() be slow
                main_orm_session.clear()
    else:
        project = M.Project.query.get(neighborhood_id=nbhd._id,
                                      shortname=options.project)
        if not project:
            return "Couldn't find project with shortname '%s'" % options.project
        update_project(options, user, project, replace_users=replace_users)


def update_project(options, user, project, replace_users=None):
    project_role = M.ProjectRole.by_name(options.group, project=project)
    if not project_role:
        return f"Couldn't find group (ProjectRole) with name '{options.group}' in {project.url()}"

    found_any_replace_users = False
    for replace_user in replace_users:
        replace_user_perm = M.ProjectRole.by_user(replace_user, project=project)
        if not replace_user_perm or project_role._id not in replace_user_perm.roles:
            log.info('Cannot replace %s they are not %s of %s', replace_user.username, options.group, project.url())
            continue
        found_any_replace_users = True
        if options.dry_run:
            log.info('Would remove %s as %s of %s', replace_user.username, options.group, project.url())
        else:
            replace_user_perm.roles.remove(project_role._id)
            if len(replace_user_perm.roles) == 0:
                # user has no roles in this project any more, so don't leave a useless doc around
                replace_user_perm.delete()
            ThreadLocalORMSession.flush_all()
    if replace_users and not found_any_replace_users:
        log.info('Not adding %s since no replace-users found on %s', user.username, project.url())
        return

    user_roles = M.ProjectRole.by_user(user, project=project, upsert=True).roles
    if project_role._id in user_roles:
        log.info('%s is already %s of %s', user.username, options.group, project.url())
        return

    if options.dry_run:
        log.info('Would add %s as %s of %s', user.username, options.group, project.url())
    else:
        user_roles.append(project_role._id)
        ThreadLocalORMSession.flush_all()


def parse_options():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('user', help='Username to add')
    parser.add_argument('group', help='Group (ProjectRole) name, e.g. Admin, '
                        'Member, Developer, etc.')
    parser.add_argument('project', nargs='?', default='--init--',
                        help='Project shortname. Default is --init-- (the neighborhood itself). '
                             'Use "ALLPROJECTS" for all projects within a neighborhood')
    parser.add_argument('--nbhd', default='/p/', help='Neighborhood '
                        'url_prefix. Default is /p/.')
    parser.add_argument('--replace-users', nargs='*',
                        help='If specified, remove these username(s) and only add the new user if one of the replace '
                             'user(s) was found and removed from each project')
    parser.add_argument('--dry-run', action='store_true',
                        help='Dry-run actions logged to log file')
    return parser.parse_args()


if __name__ == '__main__':
    import sys
    sys.exit(main(parse_options()))
