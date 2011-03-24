import sys

from ming.orm import ThreadLocalORMSession

from allura import model as M
from allura.lib import plugin

USAGE='%s <neighborhood_prefix> <neighborhood_admin0>...'

def main():
    assert len(sys.argv) > 2, USAGE
    admins = [
        M.User.by_username(un)
        for un in sys.argv[2:] ]
    prefix = sys.argv[1]
    n = M.Neighborhood(
        name=prefix,
        url_prefix='/' + prefix + '/',
        acl=dict(
            read=[None],
            create=[],
            moderate=[ u._id for u in admins ],
            admin=[ u._id for u in admins ]))
    project_reg = plugin.ProjectRegistrationProvider.get()
    project_reg.register_neighborhood_project(n, admins)
    ThreadLocalORMSession.flush_all()

if __name__ == '__main__':
    main()
