import sys
import argparse
import logging
import re
from math import pow, log10
from datetime import datetime
from contextlib import contextmanager

import faulthandler
from pylons import tmpl_context as c
from ming.orm import ThreadLocalORMSession, session

from allura import model as M
from allura.lib.utils import chunked_find, chunked_list
from allura.tasks.repo_tasks import refresh

log = logging.getLogger(__name__)


def main(options):
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
            log.info("Refreshing last commit data for project '%s'." % p.shortname)
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
                    ci_ids = list(reversed(list(c.app.repo.all_commit_ids())))
                    if options.clean:
                        if options.diffs:
                            # delete DiffInfoDocs
                            i = M.repo.DiffInfoDoc.m.find(dict(commit_ids={'$in': ci_ids})).count()
                            log.info("Deleting %i DiffInfoDoc docs, by repo id...", i)
                            M.repo.LastCommitDoc.m.remove(dict(commit_ids={'$in': ci_ids}))

                        # delete LastCommitDocs
                        i = M.repo.LastCommitDoc.m.find(dict(commit_ids={'$in': ci_ids})).count()
                        log.info("Deleting %i LastCommitDoc docs, by repo id...", i)
                        M.repo.LastCommitDoc.m.remove(dict(commit_ids={'$in': ci_ids}))

                    log.info('Refreshing all last commits in %r', c.app.repo)
                    if options.profile:
                        import cProfile
                        cProfile.runctx('refresh_repo_lcds(ci_ids, options)',
                                globals(), locals(), '/tmp/refresh_lcds.profile')
                    else:
                        refresh_repo_lcds(ci_ids, options)
                    new_commit_ids = app.repo.unknown_commit_ids()
                    if len(new_commit_ids) > 0:
                        refresh.post()
                except:
                    log.exception('Error refreshing %r', c.app.repo)
                    raise
                finally:
                    c.app.repo.status = 'ready'
                    session(c.app.repo).flush(c.app.repo)
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()


def enum_step(iter, step):
    for i,elem in enumerate(iter):
        if i % step == 0:
            yield i, elem

def refresh_repo_lcds(commit_ids, options):
    tree_cache = {}
    timings = []
    if options.diffs:
        print 'Processing diffs'
        for commit_id in commit_ids:
            commit = M.repo.Commit.query.get(_id=commit_id)
            with time(timings):
                M.repo_refresh.compute_diffs(c.app.repo._id, tree_cache, commit)
            if len(timings) % 1000 == 0:
                _print_stats(timings, 1000)
    lcd_cache = M.repo.ModelCache(
            max_instances={M.repo.LastCommit: 4000},
            max_queries={M.repo.LastCommit: 10000},
        )
    timings = []
    print 'Processing last commits'
    debug_step = int(pow(10, max(0, int(log10(len(commit_ids)) - log10(options.step) - 1))))
    _cids = commit_ids[options.skip:]
    for i, commit_id in enum_step(_cids, options.step):
        commit = M.repo.Commit.query.get(_id=commit_id)
        commit.set_context(c.app.repo)
        with time(timings):
            M.repo_refresh.compute_lcds(commit, lcd_cache)
            ThreadLocalORMSession.flush_all()
            # ensure new LCDs get fully refreshed in the cache
            # so that every commit sees the same copy
            lcd_cache.expire_new_instances(M.repo.LastCommit)
        if len(timings) % debug_step == 0:
            _print_stats(timings, debug_step)
    ThreadLocalORMSession.flush_all()


def _print_stats(timings, debug_step):
    mt = max(timings)
    tt = sum(timings)
    at = tt / len(timings)
    mat = sum(timings[-debug_step:]) / debug_step
    print '  Processed %d commits (max: %f, avg: %f, mavg: %f, tot: %f)' % (
            len(timings), mt, at, mat, tt)

@contextmanager
def time(timings):
    s = datetime.now()
    yield
    timings.append((datetime.now() - s).total_seconds())


def repo_type_list(s):
    repo_types = []
    for repo_type in s.split(','):
        repo_type = repo_type.strip()
        if repo_type not in ['git', 'hg']:
            raise argparse.ArgumentTypeError(
                    '{0} is not a valid repo type.'.format(repo_type))
        repo_types.append(repo_type)
    return repo_types


def parse_options():
    parser = argparse.ArgumentParser(description='Using existing commit data, '
            'refresh the last commit metadata in MongoDB. Run for all repos (no args), '
            'or restrict by neighborhood, project, or code tool mount point.')
    parser.add_argument('--nbhd', action='store', default='', dest='nbhd',
            help='Restrict update to a particular neighborhood, e.g. /p/.')
    parser.add_argument('--project', action='store', default='', dest='project',
            help='Restrict update to a particular project. To specify a '
            'subproject, use a slash: project/subproject.')
    parser.add_argument('--project-regex', action='store', default='',
            dest='project_regex',
            help='Restrict update to projects for which the shortname matches '
            'the provided regex.')
    parser.add_argument('--repo-types', action='store', type=repo_type_list,
            default=['git', 'hg'], dest='repo_types',
            help='Only refresh last commits for repos of the given type(s). Defaults to: '
            'git,hg. Example: --repo-types=git')
    parser.add_argument('--mount_point', default='', dest='mount_point',
            help='Restrict update to repos at the given tool mount point. ')
    parser.add_argument('--clean', action='store_true', dest='clean',
            default=False, help='Remove last commit mongo docs for '
            'project(s) being refreshed before doing the refresh.')
    parser.add_argument('--dry-run', action='store_true', dest='dry_run',
            default=False, help='Log names of projects that would have their '
            'last commits refreshed, but do not perform the actual refresh.')
    parser.add_argument('--profile', action='store_true', dest='profile',
            default=False, help='Enable the profiler (slow). Will log '
            'profiling output to ./refresh.profile')
    parser.add_argument('--diffs', action='store_true', dest='diffs',
            default=False, help='Refresh diffs as well as LCDs')
    parser.add_argument('--all', action='store_const', dest='step',
            const=1, default=100, help='Refresh the LCD for every commit instead of every 100th')
    parser.add_argument('--step', action='store', dest='step',
            type=int, default=100, help='Refresh the LCD for every Nth commit instead of every 100th')
    parser.add_argument('--skip', action='store', dest='skip',
            type=int, default=0, help='Skip a number of commits')
    return parser.parse_args()

if __name__ == '__main__':
    import sys
    faulthandler.enable()
    sys.exit(main(parse_options()))
