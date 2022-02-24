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
from datetime import datetime
from contextlib import contextmanager

import faulthandler
from tg import tmpl_context as c
from ming.orm import ThreadLocalORMSession, session

from allura import model as M
from allura.lib.utils import chunked_find
from allura.tasks.repo_tasks import refresh
from allura.scripts import ScriptTask

log = logging.getLogger(__name__)


class RefreshLastCommits(ScriptTask):

    @classmethod
    def parser(cls):
        def _repo_type_list(s):
            repo_types = []
            for repo_type in s.split(','):
                repo_type = repo_type.strip()
                if repo_type not in ['git', 'hg']:
                    raise argparse.ArgumentTypeError(
                        f'{repo_type} is not a valid repo type.')
                repo_types.append(repo_type)
            return repo_types
        parser = argparse.ArgumentParser(description='Using existing commit data, '
                                         'refresh the "last commit" metadata in MongoDB. Run for all repos (no args), '
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
            '--repo-types', action='store', type=_repo_type_list,
            default=['git', 'hg'], dest='repo_types',
            help='Only refresh last commits for repos of the given type(s). Defaults to: '
            'git,hg. Example: --repo-types=git')
        parser.add_argument('--mount-point', default='', dest='mount_point',
                            help='Restrict update to repos at the given tool mount point. ')
        parser.add_argument('--clean', action='store_true', dest='clean',
                            default=False, help='Remove last commit mongo docs for '
                            'project(s) being refreshed before doing the refresh.')
        parser.add_argument('--dry-run', action='store_true', dest='dry_run',
                            default=False, help='Log names of projects that would have their ')
        parser.add_argument('--limit', action='store', type=int, dest='limit',
                            default=False, help='Limit of how many commits to process')
        return parser

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

        log.info('Refreshing last commit data')

        for chunk in chunked_find(M.Project, q_project):
            for p in chunk:
                log.info("Refreshing last commit data for project '%s'." %
                         p.shortname)
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

                    c.app.repo.status = 'analyzing'
                    session(c.app.repo).flush(c.app.repo)
                    try:
                        ci_ids = list(
                            reversed(list(c.app.repo.all_commit_ids())))
                        if options.clean:
                            cls._clean(ci_ids)

                        log.info('Refreshing all last commits in %r',
                                 c.app.repo)
                        cls.refresh_repo_lcds(ci_ids, options)
                        new_commit_ids = app.repo.unknown_commit_ids()
                        if len(new_commit_ids) > 0:
                            refresh.post()
                    except Exception:
                        log.exception('Error refreshing %r', c.app.repo)
                        raise
                    finally:
                        c.app.repo.status = 'ready'
                        session(c.app.repo).flush(c.app.repo)
            ThreadLocalORMSession.flush_all()

    @classmethod
    def refresh_repo_lcds(cls, commit_ids, options):
        model_cache = M.repository.ModelCache(
            max_instances={M.repository.LastCommit: 4000},
            max_queries={M.repository.LastCommit: 4000},
        )
        c.model_cache = model_cache
        timings = []
        print('Processing last commits')
        for i, commit_id in enumerate(commit_ids):
            commit = M.repository.Commit.query.get(_id=commit_id)
            if commit is None:
                print("Commit missing, skipping: %s" % commit_id)
                continue
            commit.set_context(c.app.repo)
            with time(timings):
                tree = commit.tree
                cls._get_lcds(tree, model_cache)
                ThreadLocalORMSession.flush_all()
            if i % 100 == 0:
                cls._print_stats(i, timings, 100)
            if options.limit and i >= options.limit:
                break
        ThreadLocalORMSession.flush_all()

    @classmethod
    def _get_lcds(cls, tree, cache):
        M.repository.LastCommit.get(tree)
        """
        FIXME: if its needed to recurse into subdirectories, and compute their LCDs as well, something along these
        lines should be enabled.  This is not working as-is, and is not really necessary as this script doesn't
        get used any more anyway.

        for subtree in tree.tree_ids:
            if subtree.name in tree.commit.changed_paths:
                subtree_doc = cache.get(M.repository.Tree, dict(_id=subtree.id))
                subtree_doc.set_context(tree)
                cls._get_lcds(subtree_doc, cache)
        """

    @classmethod
    def _clean(cls, commit_ids):
        # delete LastCommitDocs
        i = M.repository.LastCommitDoc.m.find(
            dict(commit_id={'$in': commit_ids})).count()
        log.info("Deleting %i LastCommitDoc docs for %i commits...",
                 i, len(commit_ids))
        M.repository.LastCommitDoc.m.remove(dict(commit_id={'$in': commit_ids}))

    @classmethod
    def _print_stats(cls, processed, timings, debug_step):
        mt = max(timings)
        tt = sum(timings)
        at = tt / len(timings)
        mat = sum(timings[-debug_step:]) / debug_step
        print('  Processed %d commits (max: %f, avg: %f, mavg: %f, tot: %f)' % (
            processed, mt, at, mat, tt))


@contextmanager
def time(timings):
    s = datetime.utcnow()
    yield
    timings.append((datetime.utcnow() - s).total_seconds())


if __name__ == '__main__':
    faulthandler.enable()
    RefreshLastCommits.main()
