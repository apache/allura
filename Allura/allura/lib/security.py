"""
This module provides the security predicates used in decorating various models.
"""
from pylons import c, request
from webob import exc

def has_neighborhood_access(access_type, neighborhood, user=None):
    from allura import model as M
    def result(user=user):
        if user is None: user = c.user
        acl = neighborhood.acl[access_type]
        anon = M.User.anonymous()
        if not acl: return user != anon
        for u in acl:
            if u == anon._id or u == user._id: return True
        return False
    return result

def has_project_access(access_type, project=None, user=None):
    def result(project=project, user=user):
        if project is None: project = c.project
        if user is None: user = c.user
        assert user, 'c.user should always be at least M.User.anonymous()'
        user_roles = set(r._id for r in user.role_iter())
        for proj in project.parent_iter():
            acl = set(proj.acl.get(access_type, []))
            if acl & user_roles: return True
        if has_neighborhood_access('admin', project.neighborhood, user)():
            return True
        return False
    return result

def has_artifact_access(access_type, obj=None, user=None, app=None):
    def result(user=user, app=app):
        if user is None: user = c.user
        if app is None: app = c.app
        assert user, 'c.user should always be at least M.User.anonymous()'
        user_roles = set(r._id for r in user.role_iter())
        acl = set(app.config.acl.get(access_type, []))
        if obj is not None:
            acl |= set(obj.acl.get(access_type, []))
        if acl & user_roles: return True
        if has_neighborhood_access('admin', app.project.neighborhood, user)():
            return True
        return False
    return result

def require(predicate, message=None):
    from allura import model as M
    if predicate(): return
    if not message:
        message = """You don't have permission to do that.
                     You must ask a project administrator for rights to perform this task.
                     Please click the back button to return to the previous page."""
    if c.user != M.User.anonymous():
        request.environ['error_message'] = message
        raise exc.HTTPForbidden(detail=message)
    else:
        raise exc.HTTPUnauthorized()

def require_authenticated():
    from allura import model as M
    if c.user == M.User.anonymous():
        raise exc.HTTPUnauthorized()

def roles_with_project_access(access_type, project=None):
    '''Return all ProjectRoles' _ids who directly or transitively have the given access
    '''
    from allura import model as M
    if project is None: project = c.project
    # Direct roles
    result = set(project.acl.get(access_type, []))
    roles = M.ProjectRole.query.find().all()
    # Compute roles who can reach the direct roles
    found = True
    while found:
        found = False
        new_roles = []
        for r in roles:
            if r in result: continue
            for rr_id in r.roles:
                if rr_id in result:
                    result.add(r._id)
                    found = True
                    break
            else:
                new_roles.append(r)
        roles =new_roles
    return M.ProjectRole.query.find(dict(_id={'$in':list(result)})).all()

