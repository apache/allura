import sys
import argparse
import logging
import re
from math import pow, log10
from datetime import datetime
from contextlib import contextmanager

import faulthandler
from pylons import c
from ming.orm import ThreadLocalORMSession

from allura import model as M
from allura.lib.utils import chunked_find, chunked_list

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

                try:
                    log.info('Refreshing all last commits in %r', c.app.repo)
                    if options.profile:
                        import cProfile
                        cProfile.runctx('refresh_repo_lcds(ci_ids, options)',
                                globals(), locals(), '/tmp/refresh_lcds.profile')
                    else:
                        refresh_repo_lcds(ci_ids, options)
                except:
                    log.exception('Error refreshing %r', c.app.repo)
                    raise
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
                mt = max(timings)
                tt = sum(timings)
                at = tt / len(timings)
                print '  Processed %d commits (max: %f, avg: %f, tot: %f, cl: %d)' % (
                        len(timings), mt, at, tt, len(tree_cache))
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
        with time(timings):
            M.repo_refresh.compute_lcds(commit, lcd_cache)
            ThreadLocalORMSession.flush_all()
            # ensure new LCDs get fully refreshed in the cache
            # so that every commit sees the same copy
            lcd_cache.expire_new_instances(M.repo.LastCommit)
        if len(timings) % debug_step == 0:
            _print_stats(lcd_cache, timings, debug_step, commit)
            lcd_cache._get_walks_max = 0
            lcd_cache._build_walks_max = 0
    ThreadLocalORMSession.flush_all()


def _print_stats(lcd_cache, timings, debug_step, commit):
    mt = max(timings)
    tt = sum(timings)
    at = tt / len(timings)
    mat = sum(timings[-debug_step:]) / debug_step
    laccs = lcd_cache._accesses[M.repo.LastCommit]
    lqhits = lcd_cache._query_hits[M.repo.LastCommit]
    lqavg = lqhits * 100 / laccs if laccs > 0 else 0
    lihits = lcd_cache._instance_hits[M.repo.LastCommit]
    liavg = lihits * 100 / laccs if laccs > 0 else 0
    oaccs = sum([v for k,v in lcd_cache._accesses.items() if k != M.repo.LastCommit])
    oqhits = sum([v for k,v in lcd_cache._query_hits.items() if k != M.repo.LastCommit])
    oqavg = oqhits * 100 / oaccs if oaccs > 0 else 0
    oihits = sum([v for k,v in lcd_cache._instance_hits.items() if k != M.repo.LastCommit])
    oiavg = oihits * 100 / oaccs if oaccs > 0 else 0
    gper = lcd_cache._get_hits * 100 / lcd_cache._get_calls if lcd_cache._get_calls > 0 else 0
    print '  Processed %d commits (max: %f avg: %f mavg: %f tot: %f lq: %d/%d li: %d/%d qhit: %d/%d ihit: %d/%d mgw: %d gh: %d mbw: %d ts: %d)' % (
            len(timings), mt, at, mat, tt,
            lcd_cache.num_queries(), lcd_cache.num_queries(M.repo.LastCommit),
            lcd_cache.num_instances(), lcd_cache.num_instances(M.repo.LastCommit),
            oqavg, lqavg,
            oiavg, liavg,
            lcd_cache._get_walks_max, gper,
            lcd_cache._build_walks_max,
            len(lcd_cache.get(M.repo.TreesDoc, dict(_id=commit._id)).tree_ids))


@contextmanager
def time(timings):
    s = datetime.now()
    yield
    timings.append((datetime.now() - s).total_seconds())


def repo_type_list(s):
    repo_types = []
    for repo_type in s.split(','):
        repo_type = repo_type.strip()
        if repo_type not in ['svn', 'git', 'hg']:
            raise argparse.ArgumentTypeError(
                    '{} is not a valid repo type.'.format(repo_type))
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
            default=['svn', 'git', 'hg'], dest='repo_types',
            help='Only refresh last commits for repos of the given type(s). Defaults to: '
            'svn,git,hg. Example: --repo-types=git,hg')
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
