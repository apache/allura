"""
This module provides the security predicates used in decorating various models.
"""
from pylons import c
from webob import exc

def has_project_access(access_type, project=None):
    def result(project=project):
        if project is None: project = c.project
        user_roles = set(r._id for r in c.user.role_iter())
        for proj in project.parent_iter():
            acl = set(proj.acl.get(access_type, []))
            if acl & user_roles: return True
        return False
    return result

def has_artifact_access(access_type, obj=None):
    def result():
        user_roles = set(r._id for r in c.user.role_iter())
        acl = set(c.app.config.acl.get(access_type, []))
        if obj is not None:
            acl |= set(obj.acl.get(access_type, []))
        if acl & user_roles: return True
        return False
    return result

def require(predicate):
    from pyforge import model as M
    if predicate(): return
    if c.user != M.User.anonymous:
        raise exc.HTTPForbidden()
    else:
        raise exc.HTTPUnauthorized()

def require_authenticated():
    from pyforge import model as M
    if c.user == M.User.anonymous:
        raise exc.HTTPUnauthorized()
