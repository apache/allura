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

import six
from webob import Request
from ming.odm.odmsession import session

from allura.scripts import ScriptTask
from allura import model as M
from allura.lib import helpers as h
from allura.lib.plugin import ProjectRegistrationProvider, AuthenticationProvider

log = logging.getLogger(__name__)


class DeleteProjects(ScriptTask):

    @classmethod
    def execute(cls, options):
        provider = ProjectRegistrationProvider.get()
        auth_provider = AuthenticationProvider.get(Request.blank('/'))
        for proj in options.projects:
            proj = cls.get_project(proj)
            if proj:
                if proj.is_user_project:
                    # disable user as well
                    user = proj.user_project_of
                    if user:
                        auth_provider.disable_user(user, audit=False)
                        msg = 'Account disabled because user-project was specified for deletion. Reason: {}'.format(
                            options.reason)
                        log_entry = h.auditlog_user(msg, user=user)
                        session(log_entry).flush(log_entry)
                    else:
                        log.info('Could not find associated user for user-project %s', proj.shortname)

                log.info('Purging %s Reason: %s', proj.url(), options.reason)
                provider.purge_project(proj, disable_users=options.disable_users, reason=options.reason)

    @classmethod
    def get_project(cls, proj):
        n, p = proj.split('/', 1)
        n = M.Neighborhood.query.get(url_prefix=f'/{n}/')
        if not n:
            log.warn("Can't find neighborhood for %s", proj)
            return
        p = M.Project.query.get(neighborhood_id=n._id, shortname=n.shortname_prefix + p)
        if not p:
            log.warn("Can't find project %s", proj)
            return
        return p

    @classmethod
    def parser(cls):
        parser = argparse.ArgumentParser(description='Completely delete projects')
        parser.add_argument('projects', metavar='nbhd/project', type=str, nargs='+',
                            help='List of projects to delete in a form nbhd_prefix/shortname')
        parser.add_argument('-r', '--reason', type=lambda s: six.ensure_text(s),
                            help='Reason why these projects are being deleted')
        parser.add_argument('--disable-users', action='store_true', default=False,
                            help='Disable all users belonging to groups Admin and Developer in these projects.')
        return parser


def get_parser():
    return DeleteProjects.parser()


if __name__ == '__main__':
    DeleteProjects.main()
