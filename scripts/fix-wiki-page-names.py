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

"""Rename page/title to page-title"""

import sys
import logging

from ming.orm import session

from allura import model as M
from allura.lib import helpers as h
from allura.lib.utils import chunked_find
from forgewiki.model import Page


log = logging.getLogger(__name__)


def error(msg):
    log.error(msg)
    sys.exit(1)


def main(opts):
    if opts.project and not opts.nbhd:
        error('Specify neighborhood')
    p_query = {}
    if opts.nbhd:
        nbhd = M.Neighborhood.query.get(url_prefix=opts.nbhd)
        if not nbhd:
            error("Can't find such neighborhood")
        p_query['neighborhood_id'] = nbhd._id
        if opts.project:
            p_query['shortname'] = opts.project

        projects = M.Project.query.find(p_query).all()
        if not projects:
            error('No project matches given parameters')

        app_config_ids = []
        for p in projects:
            for ac in p.app_configs:
                if ac.tool_name.lower() == 'wiki':
                    app_config_ids.append(ac._id)

        if not app_config_ids:
            error('No wikis in given projects')
        query = {'app_config_id': {'$in': app_config_ids}}
    else:
        query = {}

    M.artifact_orm_session._get().skip_last_updated = True
    try:
        for chunk in chunked_find(Page, query):
            for page in chunk:
                if '/' in page.title:
                    log.info('Found {} in {}'.format(page.title, page.app_config.url()))
                    page.title = page.title.replace('/', '-')
                    with h.push_context(page.app_config.project._id, app_config_id=page.app_config_id):
                        session(page).flush(page)
    finally:
        M.artifact_orm_session._get().skip_last_updated = False


def parse_options():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-n', '--nbhd', default=None, help='Neighborhood url_prefix. E.g. /p/. '
                        'Default is all neighborhoods.')
    parser.add_argument('-p', '--project', default=None, help='Project shortname. '
                        'Default is all projects in given neighborhood.')
    return parser.parse_args()


if __name__ == '__main__':
    main(parse_options())
