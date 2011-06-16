"""
For projects:
    * Admin role.roles should contain Developer, and Developer only
    * Developer role.roles should contain Member, and Member only

For project.users:
    * user.project_role().roles, if it contains Admin, should not contain
      Developer or Member
    * user.project_role().roles, if it contains Developer, should not contain
      Member
"""
import sys
import logging

from pylons import c
from ming.orm import session
from ming.orm.ormsession import ThreadLocalORMSession

from allura import model as M

log = logging.getLogger(__name__)

def main():
    test = sys.argv[-1] == 'test'
    num_projects_examined = 0
    log.info('Examining subroles in all non-user projects.')
    n_users = M.Neighborhood.query.get(name='Users')
    project_filter = dict(neighborhood_id={'$ne':n_users._id})
    for some_projects in chunked_project_iterator(project_filter):
        for project in some_projects:
            project_name = '%s.%s' % (project.neighborhood.name, project.shortname)
            project_roles = {}
            for parent, child in [('Admin', 'Developer'), ('Developer', 'Member')]:
                parent_role = M.ProjectRole.by_name(parent, project=project)
                child_role = M.ProjectRole.by_name(child, project=project)
                project_roles[parent] = parent_role
                project_roles[child] = child_role
                if len(parent_role.roles) != 1 or parent_role.roles[0] != child_role._id:
                    if test:
                        log.info('Would reset %s subroles for project "%s".' % (parent, project_name))
                        log.info('- Existing %s subrole(s): %s' % (parent, parent_role.roles))
                    else:
                        log.info('Resetting %s subroles for project "%s".' % (parent, project_name))
                        parent_role.roles = [child_role._id]
                        ThreadLocalORMSession.flush_all()
            for user in project.users():
                pr = user.project_role(project=project)
                if not pr.roles: continue
                for parent, children in [('Admin', ('Developer', 'Member')), 
                                         ('Developer', ('Member',))]:
                    if project_roles[parent]._id not in pr.roles: continue
                    for role_name in children:
                        extra_role = project_roles[role_name]
                        if extra_role._id in pr.roles:
                            if test:
                                log.info('Would remove %s role from user "%s" in project "%s" (already has %s role).' \
                                         % (role_name, user.username, project_name, parent))
                                pr.roles.remove(extra_role._id)
                            else:
                                log.info('Removing %s role from user "%s" in project "%s" (already has %s role).' \
                                         % (role_name, user.username, project_name, parent))
                                pr.roles.remove(extra_role._id)
                                ThreadLocalORMSession.flush_all()
            num_projects_examined += 1
            session(project).clear()

        log.info('%s projects examined.' % num_projects_examined)


PAGESIZE=1024

def chunked_project_iterator(q_project):
    '''shamelessly copied from refresh-all-repos.py'''
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
