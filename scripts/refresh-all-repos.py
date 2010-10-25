import logging

from pylons import c

from allura import model as M
from forgegit import model as GM
from forgehg import model as HM
from forgesvn import model as SM

log = logging.getLogger(__name__)

def main():
    projects = M.Project.query.find().all()
    log.info('Refreshing repositories')
    for p in projects:
        if p.parent_id: continue
        c.project = p
        for cls in (GM.Repository, HM.Repository, SM.Repository):
            for repo in cls.query.find():
                c.app = repo.app
                try:
                    repo.refresh()
                except:
                    log.exception('Error refreshing %r', repo)
                try:
                    repo._impl._setup_receive_hook()
                except:
                    log.exception('Error setting up receive hook for %r', repo)

if __name__ == '__main__':
    main()
