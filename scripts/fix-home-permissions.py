import sys
import logging

from pylons import c
from ming.orm import session
from bson import ObjectId

from allura import model as M
from forgewiki.wiki_main import ForgeWikiApp

log = logging.getLogger('fix-home-permissions')
handler = logging.StreamHandler(sys.stdout)
log.addHandler(handler)

def main():
    test = sys.argv[-1] == 'test'

    if test:
        log.info('Examining permissions for all Home Wikis')
    else:
        log.info('Fixing permissions for all Home Wikis')

    for some_projects in chunked_project_iterator({'neighborhood_id': {'$ne': ObjectId("4be2faf8898e33156f00003e")}}):
        for project in some_projects:
            c.project = project
            home_app = project.app_instance('home')
            if isinstance(home_app, ForgeWikiApp):
                log.info('Examining permissions in project "%s".' % project.shortname)
                root_project = project.root_project or project
                authenticated_role = project_role(root_project, '*authenticated')
                member_role = project_role(root_project, 'Member')
                acl = home_app.acl

                # remove *authenticated create/update permissions
                for i, ace in enumerate(acl):
                    if ace.role_id==authenticated_role._id and ace.access==M.ACE.ALLOW and ace.permission in ('create', 'edit', 'delete'):
                        if test:
                            log.info('...would delete %s permission for role %s' % (ace.permission, authenticated_role.name))
                        else:
                            log.info('...deleting %s permission for role %s' % (ace.permission, authenticated_role.name))
                            del ace[i]

                # add member create/edit permissions
                if test:
                    log.info('...would add create permission for role %s' % member_role.name)
                    log.info('...would add update permission for role %s' % member_role.name)
                else:
                    log.info('...adding create permission for role %s' % member_role.name)
                    acl.append(M.ACE.allow(member_role._id, 'create'))
                    log.info('...adding update permission for role %s' % member_role.name)
                    acl.append(M.ACE.allow(member_role._id, 'update'))
                    session(home_app.config).flush()

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

def project_role(project, name):
    role = M.ProjectRole.query.get(project_id=project._id, name=name)
    if role is None:
        role = M.ProjectRole(project_id=project._id, name=name)
    return role

if __name__ == '__main__':
    main()
