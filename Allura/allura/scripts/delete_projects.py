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

import argparse
import logging

from ming.odm import Mapper, session
from pylons import app_globals as g
from webob import Request

from allura.scripts import ScriptTask
from allura import model as M
from allura.lib.plugin import AuthenticationProvider
from allura.tasks.index_tasks import solr_del_project_artifacts


log = logging.getLogger(__name__)


class DeleteProjects(ScriptTask):

    @classmethod
    def execute(cls, options):
        for proj in options.projects:
            proj = cls.get_project(proj)
            if proj:
                log.info('Purging %s%s. Reason: %s', proj.neighborhood.url_prefix, proj.shortname, options.reason)
                cls.purge_project(proj, options)

    @classmethod
    def get_project(cls, proj):
        n, p = proj.split('/', 1)
        n = M.Neighborhood.query.get(url_prefix='/{}/'.format(n))
        if not n:
            log.warn("Can't find neighborhood for %s", proj)
            return
        p = M.Project.query.get(neighborhood_id=n._id, shortname=p)
        if not p:
            log.warn("Can't find project %s", proj)
            return
        return p

    @classmethod
    def purge_project(cls, project, options):
        pid = project._id
        solr_del_project_artifacts.post(pid)
        if options.disable_users:
            # Disable users if necessary BEFORE removing all project-related documents
            cls.disable_users(project, options)
        app_config_ids = [ac._id for ac in M.AppConfig.query.find(dict(project_id=pid))]
        for m in Mapper.all_mappers():
            mcls = m.mapped_class
            if 'project_id' in m.property_index:
                # Purge the things directly related to the project
                mcls.query.remove(dict(project_id=pid))
            elif 'app_config_id' in m.property_index:
                # ... and the things related to its apps
                mcls.query.remove(dict(app_config_id={'$in': app_config_ids}))
        project.delete()
        session(project).flush()
        g.post_event('project_deleted', project_id=pid, reason=options.reason)

    @classmethod
    def disable_users(cls, project, options):
        provider = AuthenticationProvider.get(Request.blank('/'))
        users = project.admins() + project.users_with_role('Developer')
        for user in users:
            if user.disabled:
                continue
            log.info(u'Disabling user %s', user.username)
            provider.disable_user(user, audit=False)
            msg = u'Account disabled because project {}{} is deleted. Reason: {}'.format(
                project.neighborhood.url_prefix,
                project.shortname,
                options.reason)
            M.AuditLog.log_user(msg, user=user)
            # `users` can contain duplicates. Make sure changes are visible
            # to next iterations, so that `user.disabled` check works.
            session(user).expunge(user)

    @classmethod
    def parser(cls):
        parser = argparse.ArgumentParser(description='Completely delete projects')
        parser.add_argument('projects', metavar='nbhd/project', type=str, nargs='+',
                            help='List of projects to delete in a form nbhd_prefix/shortname')
        parser.add_argument('-r', '--reason', type=str,
                            help='Reason why these projects are being deleted')
        parser.add_argument('--disable-users', action='store_true', default=False,
                            help='Disable all users belonging to groups Admin and Developer in these projects.')
        return parser


def get_parser():
    return DeleteProjects.parser()


if __name__ == '__main__':
    DeleteProjects.main()
