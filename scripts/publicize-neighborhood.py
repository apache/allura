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

import logging
import sys

from ming.orm import ThreadLocalORMSession
from tg import tmpl_context as c, app_globals as g

from allura import model as M
from allura.lib import helpers as h
from allura.lib import utils

log = logging.getLogger(__name__)


def main(options):
    log.addHandler(logging.StreamHandler(sys.stdout))
    log.setLevel(getattr(logging, options.log_level.upper()))

    nbhd = M.Neighborhood.query.get(name=options.neighborhood)
    if not nbhd:
        return 'Invalid neighborhood "%s".' % options.neighborhood
    admin_role = M.ProjectRole.by_name(
        'Admin', project=nbhd.neighborhood_project)
    nbhd_admin = admin_role.users_with_role(
        project=nbhd.neighborhood_project)[0].user
    log.info('Making updates as neighborhood admin "%s"' % nbhd_admin.username)

    q = {'neighborhood_id': nbhd._id,
         'is_nbhd_project': False, 'deleted': False}
    private_count = public_count = 0
    for projects in utils.chunked_find(M.Project, q):
        for p in projects:
            role_anon = M.ProjectRole.upsert(name='*anonymous',
                                             project_id=p.root_project._id)
            if M.ACE.allow(role_anon._id, 'read') not in p.acl:
                if options.test:
                    log.info('Would be made public: "%s"' % p.shortname)
                else:
                    log.info('Making public: "%s"' % p.shortname)
                    p.acl.append(M.ACE.allow(role_anon._id, 'read'))
                    with h.push_config(c, project=p, user=nbhd_admin):
                        ThreadLocalORMSession.flush_all()
                        g.post_event('project_updated')
                private_count += 1
            else:
                log.info('Already public: "%s"' % p.shortname)
                public_count += 1

    log.info('Already public: %s' % public_count)
    if options.test:
        log.info('Would be made public: %s' % private_count)
    else:
        log.info('Made public: %s' % private_count)
    return 0


def parser():
    import argparse
    parser = argparse.ArgumentParser(
        description='Make all projects in a neighborhood public.')
    parser.add_argument('neighborhood', metavar='NEIGHBORHOOD', type=str,
                        help='Neighborhood name.')
    parser.add_argument('--test', dest='test', default=False,
                        action='store_true',
                        help='Run in test mode (no updates will be applied).')
    parser.add_argument('--log', dest='log_level', default='INFO',
                        help='Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).')
    return parser


def parse_options():
    return parser().parse_args()


if __name__ == '__main__':
    sys.exit(main(parse_options()))
