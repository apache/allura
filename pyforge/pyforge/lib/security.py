"""
This module provides the security predicates used in decorating various models.
"""
from pylons import c
from webob import exc

def has_forge_access(obj, access_type):
    '''Verify that the current user has the required permissions to perform
    project-level operations (create/delete project, install/remove plugins,
    modify security).
    '''

    if not c.user:
        return False
    for role in obj.acl[access_type]:
        if c.user._id == role:
            return True
    return False
    
def has_project_access(obj, access_type):
    '''Verify that the current user has the required permissions to perform
    plugin- and artifact- level operations.  Plugin- and artifact- level
    operations are defined by each plugin in its permissions field.

    We also provide special psuedo-roles '*anonymous' and '*authenticated' to allow
    any user and any authenticated user access to the given resource.  Note that
    *authenticated is implied by *anonymous.
    '''

    acl = set(obj.acl.get(access_type, []))
    if not acl:
        acl = set(c.app.config.acl.get(access_type, []))
    if '*anonymous' in acl: return True
    if not c.user:
        return False
    if '*authenticated' in acl: return True
    for r in c.user.role_iter():
        if r in acl: return True
    return False

def require_forge_access(obj, access_type):
    if has_forge_access(obj, access_type): return
    if c.user:
        raise exc.HTTPForbidden()
    else:
        raise exc.HTTPUnauthorized()

def require_project_access(obj, access_type):
    if has_project_access(obj, access_type): return
    if c.user:
        raise exc.HTTPForbidden()
    else:
        raise exc.HTTPUnauthorized()

def require_authenticated():
    if not c.user:
        raise exc.HTTPUnauthorized()
