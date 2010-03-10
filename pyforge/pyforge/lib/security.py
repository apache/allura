"""
This module provides the security predicates used in decorating various models.
"""
from pylons import c, request
from webob import exc

def has_neighborhood_access(access_type, neighborhood, user=None):
    from pyforge import model as M
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
    from pyforge import model as M
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
    from pyforge import model as M
    if c.user == M.User.anonymous():
        raise exc.HTTPUnauthorized()
