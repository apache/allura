import logging
import optparse
from collections import defaultdict

from pylons import c
from ming.orm import ThreadLocalORMSession

from allura import model as M

log = logging.getLogger(__name__)

PAGESIZE=1024

def main():
    parser = optparse.OptionParser()
    parser.add_option(
        '--clean', action='store_true', dest='clean', default=False,
        help='remove all RepoObjects before refresh')
    parser.add_option(
        '--all', action='store_true', dest='all', default=False,
        help='refresh all commits (not just the ones that are new')
    options, args = parser.parse_args()
    if args:
        projects = defaultdict(list)
        for path in args:
            shortname, mount_point = path.rsplit('/', 1)
            projects[shortname].append(mount_point)
        q_project = dict(shortname={'$in': projects.keys()})
    else:
        projects = {}
        q_project = {}
    log.info('Refreshing repositories')
    if options.clean:
        log.info('Removing all repository objects')
        M.repository.RepoObject.query.remove()
    for chunk in chunked_project_iterator(q_project):
        for p in chunk:
            c.project = p
            if projects:
                mount_points = projects[p.shortname]
            else:
                mount_points = [ ac.options.mount_point
                                 for ac in M.AppConfig.query.find(dict(project_id=p._id)) ]
            for app in (p.app_instance(mp) for mp in mount_points):
                c.app = app
                if not hasattr(app, 'repo'): continue
                if options.clean:
                    M.LastCommitFor.query.remove(dict(repo_id=c.app.repo._id))
                try:
                    c.app.repo._impl._setup_hooks()
                except:
                    log.exception('Error setting up hooks for %r', c.app.repo)
                try:
                    if options.all:
                        log.info('Refreshing ALL commits in %r', c.app.repo)
                    else:
                        log.info('Refreshing NEW commits in %r', c.app.repo)
                    c.app.repo.refresh(options.all)
                except:
                    log.exception('Error refreshing %r', c.app.repo)
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

def chunked_project_iterator(q_project):
    page = 0
    while True:
        results = (M.Project.query
                   .find(q_project)
                   .skip(PAGESIZE*page)
                   .limit(PAGESIZE)
                   .all())
        if not results: break
        yield results
        page += 1
    

if __name__ == '__main__':
    main()
