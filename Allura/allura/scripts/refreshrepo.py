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
import faulthandler
from datetime import datetime

from paste.util.converters import asbool
from tg import tmpl_context as c
from ming.orm import ThreadLocalORMSession

from allura import model as M
from allura.lib.utils import chunked_find, chunked_list
from allura.scripts import ScriptTask

log = logging.getLogger(__name__)


class RefreshRepo(ScriptTask):

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

        log.info('Refreshing repositories')
        for chunk in chunked_find(M.Project, q_project):
            for p in chunk:
                log.info("Refreshing repos for project '%s'." % p.shortname)
                if options.dry_run:
                    continue
                c.project = p
                if options.mount_point:
                    mount_points = [options.mount_point]
                else:
                    mount_points = [ac.options.mount_point for ac in
                                    M.AppConfig.query.find(dict(project_id=p._id))]
                for app in (p.app_instance(mp) for mp in mount_points):
                    c.app = app
                    if not hasattr(app, 'repo'):
                        continue
                    if c.app.repo.tool.lower() not in options.repo_types:
                        log.info("Skipping %r: wrong type (%s)", c.app.repo,
                                 c.app.repo.tool.lower())
                        continue

                    ci_ids = []
                    if options.clean:
                        ci_ids = list(c.app.repo.all_commit_ids())
                    elif options.clean_after:
                        for ci in M.repository.CommitDoc.m.find({'repo_ids': c.app.repo._id,
                                                                 'committed.date': {'$gt': options.clean_after}}):
                            ci_ids.append(ci._id)

                    if ci_ids:
                        log.info("Deleting mongo data for %i commits...",
                                 len(ci_ids))
                        # delete these in chunks, otherwise the query doc can
                        # exceed the max BSON size limit (16MB at the moment)
                        for ci_ids_chunk in chunked_list(ci_ids, 3000):
                            i = M.repository.CommitDoc.m.find(
                                {"_id": {"$in": ci_ids_chunk}}).count()
                            if i:
                                log.info("Deleting %i CommitDoc docs...", i)
                                M.repository.CommitDoc.m.remove(
                                    {"_id": {"$in": ci_ids_chunk}})

                        for ci_ids_chunk in chunked_list(ci_ids, 3000):
                            # delete LastCommitDocs
                            i = M.repository.LastCommitDoc.m.find(
                                dict(commit_id={'$in': ci_ids_chunk})).count()
                            if i:
                                log.info(
                                    "Deleting %i LastCommitDoc docs...", i)
                                M.repository.LastCommitDoc.m.remove(
                                    dict(commit_id={'$in': ci_ids_chunk}))

                        del ci_ids

                    try:
                        if options.all:
                            log.info('Refreshing ALL commits in %r',
                                     c.app.repo)
                        else:
                            log.info('Refreshing NEW commits in %r',
                                     c.app.repo)
                        if options.profile:
                            import cProfile
                            cProfile.runctx(
                                'c.app.repo.refresh(options.all, notify=options.notify, '
                                '   commits_are_new=options.commits_are_new)',
                                globals(), locals(), 'refresh.profile')
                        else:
                            c.app.repo.refresh(
                                options.all, notify=options.notify, commits_are_new=options.commits_are_new)
                    except Exception:
                        log.exception('Error refreshing %r', c.app.repo)
            ThreadLocalORMSession.flush_all()

    @classmethod
    def parser(cls):
        def repo_type_list(s):
            repo_types = []
            for repo_type in s.split(','):
                repo_type = repo_type.strip()
                if repo_type not in ['svn', 'git', 'hg']:
                    raise argparse.ArgumentTypeError(
                        f'{repo_type} is not a valid repo type.')
                repo_types.append(repo_type)
            return repo_types

        date_format = '%Y-%m-%dT%H:%M:%S'

        parser = argparse.ArgumentParser(description='Scan repos on filesytem and '
                                         'update repo metadata in MongoDB. Run for all repos (no args), '
                                         'or restrict by neighborhood, project, or code tool mount point.')
        parser.add_argument('--nbhd', action='store', default='', dest='nbhd',
                            help='Restrict update to a particular neighborhood, e.g. /p/.')
        parser.add_argument(
            '--project', action='store', default='', dest='project',
            help='Restrict update to a particular project. To specify a '
            'subproject, use a slash: project/subproject.')
        parser.add_argument('--project-regex', action='store', default='',
                            dest='project_regex',
                            help='Restrict update to projects for which the shortname matches '
                            'the provided regex.')
        parser.add_argument(
            '--repo-types', action='store', type=repo_type_list,
            default=['svn', 'git', 'hg'], dest='repo_types',
            help='Only refresh repos of the given type(s). Defaults to: '
            'svn,git,hg. Example: --repo-types=git,hg')
        parser.add_argument('--mount-point', default='', dest='mount_point',
                            help='Restrict update to repos at the given tool mount point. ')
        parser.add_argument('--clean', action='store_true', dest='clean',
                            default=False, help='Remove repo-related mongo docs (for '
                            'project(s) being refreshed only) before doing the refresh.')
        parser.add_argument('--clean-after', metavar='DATETIME', dest='clean_after',
                            type=lambda d: datetime.strptime(d, date_format),
                            help='Like --clean but only docs for commits after date ({} format)'.format(
                                    date_format.replace('%', '%%')
                            ))
        parser.add_argument(
            '--all', action='store_true', dest='all', default=False,
            help='Refresh all commits (not just the ones that are new).')
        parser.add_argument('--notify', action='store_true', dest='notify',
                            default=False, help='Send email notifications of new commits.')
        parser.add_argument('--commits-are-new', dest='commits_are_new',
                            type=asbool, metavar='true/false', default=None,
                            help='Specify true/false to override smart default.  Controls creating activity entries, '
                                 'stats, sending webhook etc.')
        parser.add_argument('--dry-run', action='store_true', dest='dry_run',
                            default=False, help='Log names of projects that would have their '
                            'repos refreshed, but do not perform the actual refresh.')
        parser.add_argument('--profile', action='store_true', dest='profile',
                            default=False, help='Enable the profiler (slow). Will log '
                            'profiling output to ./refresh.profile')
        return parser


def get_parser():
    return RefreshRepo.parser()


if __name__ == '__main__':
    faulthandler.enable()
    RefreshRepo.main()
