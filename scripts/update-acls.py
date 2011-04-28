import sys
import logging
from pprint import pformat

from ming.orm import ThreadLocalORMSession

from allura import model as M
from allura.command.show_models import dfs, build_model_inheritance_graph

TEST=False

log = logging.getLogger('update-acls')

def main():
    global TEST
    if len(sys.argv) > 1:
        TEST = True
        assert len(sys.argv) == 2
        assert sys.argv[1] == 'test'
    # Update project acls
    log.info('====================================')
    log.info('Update project ACLs')
    neighborhood = M.main_doc_session.db.neighborhood
    project = M.main_doc_session.db.project
    app_config = M.project_doc_session.db.config
    for p in project.find():
        update_project_acl(p)
        if not TEST: project.save(p)
    # Update neighborhood acls
    log.info('====================================')
    log.info('Update neighborhood ACLs')
    for n in neighborhood.find():
        p = project.find(dict(
                neighborhood_id=n['_id'], shortname='--init--')).next()
        update_neighborhood_acl(n, p)
        if not TEST:
            neighborhood.save(n)
            project.save(p)
            ThreadLocalORMSession.flush_all()
            ThreadLocalORMSession.close_all()
    # Update app config acls
    log.info('====================================')
    log.info('Update appconfig ACLs')
    for ac in app_config.find():
        simple_acl_update(ac)
        if not TEST: app_config.save(ac)
    # Update artifact acls
    log.info('====================================')
    log.info('Update artifact ACLs')
    graph = build_model_inheritance_graph()
    for _, a_cls in dfs(M.Artifact, graph):
        artifact = M.project_doc_session.db[
            a_cls.__mongometa__.name]
        for a in artifact.find():
            empty_acl = not a['acl']
            simple_acl_update(a)
            if not TEST and not empty_acl: artifact.save(a)

def update_project_acl(project_doc):
    '''Convert the old dict-style ACL to a list of ALLOW ACEs. Also move the
    security,tool,delete perms to 'admin'
    '''
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
            _grant(new_acl, perm, rid)
    if TEST:
        log.info('--- update %s\n%s\n%s\n---',
                 project_doc['shortname'],
                 pformat(_format_acd(project_doc['acl'])),
                 pformat(map(_format_ace, new_acl)))
    project_doc['acl'] = new_acl

def update_neighborhood_acl(neighborhood_doc, init_doc):
    '''Convert nbhd admins users to --init-- project admins'''
    if 'acl' not in neighborhood_doc:
        log.warning('Neighborhood %s is already updated' % neighborhood_doc['name'])
        return

    if TEST: log.info('Update nbhd %s', neighborhood_doc['name'])
    if 'acl' not in neighborhood_doc:
        log.warning('Neighborhood %s already updated', neighborhood_doc['name'])
    pid = init_doc['_id']
    r_auth = M.ProjectRole.authenticated(pid)._id
    r_admin = M.ProjectRole.by_name('Admin', pid)._id
    acl = neighborhood_doc['acl']
    new_acl = list(init_doc['acl'])
    assert acl['read'] == [None] # nbhd should be public
    for uid in acl['admin'] + acl['moderate']:
        u = M.User.query.get(_id=uid)
        if TEST: log.info('... grant nbhd admin to: %s', u.username)
        role =  M.ProjectRole.upsert(user_id=uid, project_id=init_doc['_id'])
        if r_admin not in role.roles:
            role.roles.append(r_admin)
    _grant(new_acl, 'register', r_admin)
    if acl['create'] == [ ]:
        if TEST: log.info('grant register to auth')
        _grant(new_acl, 'register', r_auth)
    del neighborhood_doc['acl']
    if TEST:
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
    if TEST and doc['acl']:
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
    return role.name or role.user.username

def _format_acd(acd):
    return dict(
        (k, map(_format_role, v))
        for k,v in acd.iteritems())

if __name__ == '__main__':
    main()
