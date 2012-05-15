import logging
import optparse

from pylons import c
from ming.orm import ThreadLocalORMSession

from allura import model as M
from allura.lib import utils

log = logging.getLogger(__name__)

PAGESIZE=1024

def main():
    parser = optparse.OptionParser(usage="""%prog -- [options] [/p/ someproject/optional-subproj mount-point]\n\n
        Specify a neighborhood url-prefix, project shortname, and mountpoint to run for just one repo.  Omit that
        to run for all repos.
    """)
    parser.add_option(
        '--clean', action='store_true', dest='clean', default=False,
        help='remove all RepoObjects before refresh')
    parser.add_option(
        '--all', action='store_true', dest='all', default=False,
        help='refresh all commits (not just the ones that are new')
    parser.add_option(
        '--notify', action='store_true', dest='notify', default=False,
        help='send email notifications of new commits')
    options, args = parser.parse_args()
    if args:
        nbhd = M.Neighborhood.query.get(url_prefix=args[0])
        shortname = args[1]
        mount_point = args[2]
        q_project = {'shortname': shortname, 'neighborhood_id': nbhd._id}
        projects = {shortname:[mount_point]}
    else:
        projects = {}
        q_project = {}
    log.info('Refreshing repositories')
    if options.clean:
        log.info('Removing all repository objects')
        M.repository.RepoObject.query.remove()
        M.repo.CommitDoc.m.remove({})
        M.repo.TreeDoc.m.remove({})
        M.repo.TreesDoc.m.remove({})
        M.repo.DiffInfoDoc.m.remove({})
        M.repo.LastCommitDoc.m.remove({})
        M.repo.CommitRunDoc.m.remove({})
    for chunk in utils.chunked_find(M.Project, q_project):
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
                    c.app.repo.refresh(options.all, notify=options.notify)
                except:
                    log.exception('Error refreshing %r', c.app.repo)
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

if __name__ == '__main__':
    main()
