"""
This module provides the security predicates used in decorating various models.
"""
from pylons import c, response, request
from webob import exc

def has_project_access(access_type, project=None, user=None):
    def result(project=project, user=user):
        if project is None: project = c.project
        if user is None: user = c.user
        user_roles = set(r._id for r in user.role_iter())
        for proj in project.parent_iter():
            acl = set(proj.acl.get(access_type, []))
            if acl & user_roles: return True
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
        return False
    return result

def require(predicate, message='Forbidden'):
    from pyforge import model as M
    if predicate(): return
    if c.user != M.User.anonymous:
        request.environ['error_message'] = message
        raise exc.HTTPForbidden(detail=message)
    else:
        raise exc.HTTPUnauthorized()

def require_authenticated():
    from pyforge import model as M
    if c.user == M.User.anonymous:
        raise exc.HTTPUnauthorized()
