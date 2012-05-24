import logging

import faulthandler
from pylons import c
from ming.orm import ThreadLocalORMSession

from allura import model as M
from allura.lib.utils import chunked_find

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

    log.info('Refreshing repositories')
    if options.clean:
        log.info('Removing all repository objects')
        M.repo.CommitDoc.m.remove({})
        M.repo.TreeDoc.m.remove({})
        M.repo.TreesDoc.m.remove({})
        M.repo.DiffInfoDoc.m.remove({})
        M.repo.CommitRunDoc.m.remove({})

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
                if not hasattr(app, 'repo'): continue
                try:
                    c.app.repo._impl._setup_hooks()
                except:
                    log.exception('Error setting up hooks for %r', c.app.repo)
                try:
                    if options.all:
                        log.info('Refreshing ALL commits in %r', c.app.repo)
                    else:
                        log.info('Refreshing NEW commits in %r', c.app.repo)
                    c.app.repo.refresh(options.all, notify=options.notify)
                except:
                    log.exception('Error refreshing %r', c.app.repo)
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

def parse_options():
    import argparse
    parser = argparse.ArgumentParser(description='Scan repos on filesytem and '
            'update repo metadata in MongoDB. Run for all repos (no args), '
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
    parser.add_argument('--mount_point', default='', dest='mount_point',
            help='Restrict update to repos at the given tool mount point. ')
    parser.add_argument('--clean', action='store_true', dest='clean',
            default=False, help='Remove all repo-related mongo docs before '
            'refresh.')
    parser.add_argument('--all', action='store_true', dest='all', default=False,
            help='Refresh all commits (not just the ones that are new).')
    parser.add_argument('--notify', action='store_true', dest='notify',
            default=False, help='Send email notifications of new commits.')
    parser.add_argument('--dry-run', action='store_true', dest='dry_run',
            default=False, help='Log names of projects that would have their '
            'repos refreshed, but do not perform the actual refresh.')
    return parser.parse_args()

if __name__ == '__main__':
    import sys
    faulthandler.enable()
    sys.exit(main(parse_options()))
