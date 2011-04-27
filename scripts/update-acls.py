import logging
from optparse import OptionParser
from pprint import pformat

from pylons import c
from ming.base import Object
from ming.orm import ThreadLocalORMSession

from allura import model as M
from allura.command.show_models import dfs, build_model_inheritance_graph

log = logging.getLogger('update-acls')

options = None
optparser = OptionParser(usage='allurapaste script <ini file> -- %prog [options] [neighborhood1...]')
optparser.add_option('-t', '--test',  dest='test', action='store_true')

def main():
    global options
    options, neighborhoods = optparser.parse_args()
    neighborhood = M.main_doc_session.db.neighborhood
    project = M.main_doc_session.db.project
    c.project = Object(
        database_uri=project.find().next()['database_uri'])
    app_config = M.project_doc_session.db.config
    if neighborhoods:
        log.info('Updating neighborhoods: %s', neighborhoods)
        q_neighborhoods = list(neighborhood.find(dict(name={'$in': neighborhoods })))
        neighborhood_ids=[ n['_id'] for n in q_neighborhoods ]
        q_projects = list(project.find(dict(neighborhood_id={'$in': neighborhood_ids})))
        project_ids = list(p['_id'] for p in q_projects)
        q_app_config = list(app_config.find(dict(project_id={'$in': project_ids})))
        log.info('... %d neighborhoods', len(q_neighborhoods))
        log.info('... %d projects', len(q_projects))
        log.info('... %d app configs', len(q_app_config))
    else:
        q_neighborhoods = neighborhood.find()
        q_projects = project.find()
        q_app_config = app_config.find()
        log.info('Updating all neighborhoods')
    # Update project acls
    log.info('====================================')
    log.info('Update project ACLs')
    for p in q_projects:
        update_project_acl(p)
        if not options.test: project.save(p)
    # Update neighborhood acls
    log.info('====================================')
    log.info('Update neighborhood ACLs')
    for n in q_neighborhoods:
        p = project.find(dict(
                neighborhood_id=n['_id'], shortname='--init--')).next()
        update_neighborhood_acl(n, p)
        if not options.test:
            neighborhood.save(n)
            project.save(p)
            ThreadLocalORMSession.flush_all()
            ThreadLocalORMSession.close_all()
    graph = build_model_inheritance_graph()
    # Update app config acls
    log.info('====================================')
    log.info('Update appconfig ACLs')
    for ac in q_app_config:
        simple_acl_update(ac)
        if not options.test: app_config.save(ac)
        # Update artifact acls
        log.info('====================================')
        log.info('Update artifact ACLs')
        for _, a_cls in dfs(M.Artifact, graph):
            artifact = M.project_doc_session.db[
                a_cls.__mongometa__.name]
            for a in artifact.find(dict(app_config_id=ac['_id'])):
                empty_acl = not a['acl']
                simple_acl_update(a)
                if not options.test and not empty_acl: artifact.save(a)

def update_project_acl(project_doc):
    '''Convert the old dict-style ACL to a list of ALLOW ACEs. Also move the
    security,tool,delete perms to 'admin'
    '''
    project_role = M.project_doc_session.db.project_role
    if not isinstance(project_doc['acl'], dict):
        log.warning('Project %s is already updated', project_doc['shortname'])
        return
    perm_map = dict(
        read='read',
        create='create',
        update='update',
        security='admin',
        tool='admin',
        delete='admin')
    new_acl = []
    for perm, role_ids in sorted(project_doc['acl'].iteritems()):
        perm = perm_map[perm]
        for rid in role_ids:
            if project_role.find(dict(_id=rid)).count() == 0: continue
            _grant(new_acl, perm, rid)
    if options.test:
        log.info('--- update %s\n%s\n%s\n---',
                 project_doc['shortname'],
                 pformat(_format_acd(project_doc['acl'])),
                 pformat(map(_format_ace, new_acl)))
    project_doc['acl'] = new_acl

def update_neighborhood_acl(neighborhood_doc, init_doc):
    '''Convert nbhd admins users to --init-- project admins'''
    if options.test: log.info('Update nbhd %s', neighborhood_doc['name'])
    if 'acl' not in neighborhood_doc:
        log.warning('Neighborhood %s already updated', neighborhood_doc['name'])
    p = Object(init_doc)
    p.root_project=p
    r_auth = M.ProjectRole.authenticated(p)._id
    r_admin = M.ProjectRole.by_name('Admin', p)._id
    acl = neighborhood_doc['acl']
    new_acl = list(init_doc['acl'])
    assert acl['read'] == [None] # nbhd should be public
    for uid in acl['admin'] + acl['moderate']:
        u = M.User.query.get(_id=uid)
        if options.test: log.info('... grant nbhd admin to: %s', u.username)
        role =  M.ProjectRole.upsert(user_id=uid, project_id=init_doc['_id'])
        if r_admin not in role.roles:
            role.roles.append(r_admin)
    _grant(new_acl, 'register', r_admin)
    if acl['create'] == [ ]:
        if options.test: log.info('grant register to auth')
        _grant(new_acl, 'register', r_auth)
    del neighborhood_doc['acl']
    if options.test:
        log.info('--- new init acl:\n%s\n%s\n---',
                 pformat(_format_acd(init_doc['acl'])),
                 pformat(map(_format_ace, new_acl)))
    init_doc['acl'] = new_acl

def simple_acl_update(doc):
    '''Update dict-style to list-style ACL'''
    if not isinstance(doc['acl'], dict):
        log.warning('Already upgraded %s' % doc)
        return

    new_acl = []
    for perm, role_ids in sorted(doc['acl'].iteritems()):
        for rid in role_ids:
            _grant(new_acl, perm, rid)
    if options.test and doc['acl']:
        log.info('--- update\n%s\n%s\n---',
                 pformat(_format_acd(doc['acl'])),
                 pformat(map(_format_ace, new_acl)))
    doc['acl'] = new_acl

def _grant(acl, permission, role_id):
    ace = dict(
        access='ALLOW',
        permission=permission,
        role_id=role_id)
    if ace not in acl:
        acl.append(ace)

def _format_ace(ace):
    if isinstance(ace, basestring): return ace
    return '(%s, %s, %s)' % (
        ace['access'], ace['permission'], _format_role(ace['role_id']))

def _format_role(rid):
    role = M.ProjectRole.query.get(_id=rid)
    if role:
        if role.name:
            return role.name
        if role.user:
            return role.user.username
    return '--invalid--'

def _format_acd(acd):
    return dict(
        (k, map(_format_role, v))
        for k,v in acd.iteritems())

if __name__ == '__main__':
    main()
