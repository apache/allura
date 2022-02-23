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

from pymongo.errors import InvalidDocument
from tg import tmpl_context as c, app_globals as g

from allura.scripts import ScriptTask
from allura import model as M
from allura.tasks.index_tasks import add_projects
from allura.lib.utils import chunked_find, chunked_list
from allura.lib.exceptions import CompoundError


log = logging.getLogger(__name__)


class ReindexProjects(ScriptTask):

    @classmethod
    def execute(cls, options):
        q_project = {}
        if options.nbhd:
            nbhd = M.Neighborhood.query.get(url_prefix=options.nbhd)
            if not nbhd:
                return "Invalid neighborhood url prefix."
            q_project['neighborhood_id'] = nbhd._id
        if options.project:
            q_project['shortname'] = options.project
        elif options.project_regex:
            q_project['shortname'] = {'$regex': options.project_regex}

        for chunk in chunked_find(M.Project, q_project):
            project_ids = []
            for p in chunk:
                log.info('Reindex project %s', p.shortname)
                if options.dry_run:
                    continue
                c.project = p
                project_ids.append(p._id)

            try:
                for chunk in chunked_list(project_ids, options.max_chunk):
                    if options.tasks:
                        cls._post_add_projects(chunk)
                    else:
                        add_projects(chunk)
            except CompoundError as err:
                log.exception('Error indexing projects:\n%r', err)
                log.error('%s', err.format_error())
            M.main_orm_session.flush()
            M.main_orm_session.clear()
        log.info('Reindex %s', 'queued' if options.tasks else 'done')

    @classmethod
    def _post_add_projects(cls, chunk):
        """
        Post task, recursively splitting and re-posting if the resulting
        mongo document is too large.
        """
        try:
            add_projects.post(chunk)
        except InvalidDocument as e:
            # there are many types of InvalidDocument, only recurse if its
            # expected to help
            if e.args[0].startswith('BSON document too large'):
                cls._post_add_projects(chunk[:len(chunk) // 2])
                cls._post_add_projects(chunk[len(chunk) // 2:])
            else:
                raise

    @classmethod
    def parser(cls):
        parser = argparse.ArgumentParser(description='Reindex all project records into Solr (for searching)')
        parser.add_argument('-n', '--nbhd', action='store', default='', dest='nbhd',
                            help='Restrict reindex to a particular neighborhood, e.g. /p/.')
        parser.add_argument(
            '-p', '--project', action='store', default='', dest='project',
            help='Restrict update to a particular project. To specify a '
            'subproject, use a slash: project/subproject.')
        parser.add_argument('--project-regex', action='store', default='',
                            dest='project_regex',
                            help='Restrict update to projects for which the shortname matches '
                            'the provided regex.')
        parser.add_argument('--dry-run', action='store_true', dest='dry_run',
                            default=False, help='Log names of projects that would be reindexed, '
                            'but do not perform the actual reindex.')
        parser.add_argument('--tasks', action='store_true', dest='tasks',
                            help='Run each individual index operation as a background task.')
        parser.add_argument(
            '--max-chunk', dest='max_chunk', type=int, default=100 * 1000,
            help='Max number of artifacts to index in one Solr update command')
        return parser


def get_parser():
    return ReindexProjects.parser()


if __name__ == '__main__':
    ReindexProjects.main()
