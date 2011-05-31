"""
This module provides the security predicates used in decorating various models.
"""
import logging
from collections import defaultdict

from pylons import c, request
from webob import exc
from itertools import chain
from ming.utils import LazyProperty

from allura.lib.utils import TruthyCallable

log = logging.getLogger(__name__)

class Credentials(object):
    '''
    Role graph logic & caching
    '''

    def __init__(self):
        self.clear()

    @classmethod
    def get(cls):
        'get the global Credentials instance'
        import allura
        return allura.credentials

    def clear(self):
        'clear cache'
        self.users = {}
        self.projects = {}

    def load_user_roles(self, user_id, *project_ids):
        '''Load the credentials with all user roles for a set of projects'''
        from allura import model as M
        # Don't reload roles
        project_ids = [ pid for pid in project_ids if self.users.get((user_id, pid)) is None ]
        if not project_ids: return 
        if user_id is None:
            q = M.ProjectRole.query.find(
                dict(
                    project_id={'$in': project_ids},
                    name='*anonymous'))
        else:
            q0 = M.ProjectRole.query.find(
                dict(project_id={'$in': list(project_ids)},
                     name={'$in':['*anonymous', '*authenticated']}))
            q1 = M.ProjectRole.query.find(
                        dict(project_id={'$in': list(project_ids)},user_id=user_id))
            q = chain(q0, q1)
        roles_by_project = dict((pid, []) for pid in project_ids)
        for role in q:
            roles_by_project[role.project_id].append(role)
        for pid, roles in roles_by_project.iteritems():
            self.users[user_id, pid] = RoleCache(self, roles)

    def load_project_roles(self, *project_ids):
        '''Load the credentials with all user roles for a set of projects'''
        from allura import model as M
        # Don't reload roles
        project_ids = [ pid for pid in project_ids if self.projects.get(pid) is None ]
        if not project_ids: return 
        q = M.ProjectRole.query.find(dict(
                project_id={'$in': project_ids}))
        roles_by_project = dict((pid, []) for pid in project_ids)
        for role in q:
            roles_by_project[role.project_id].append(role)
        for pid, roles in roles_by_project.iteritems():
            self.projects[pid] = RoleCache(self, roles)

    def project_roles(self, project_id):
        '''
        :returns: a RoleCache of ProjectRoles for project_id
        '''
        roles = self.projects.get(project_id)
        if roles is None:
            self.load_project_roles(project_id)
            roles = self.projects[project_id]
        return roles

    def user_roles(self, user_id, project_id=None):
        '''
        :returns: a RoleCache of ProjectRoles for given user_id and project_id, *anonymous and *authenticated checked as appropriate
        '''
        from allura import model as M
        roles = self.users.get((user_id, project_id))
        if roles is None:
            if project_id is None:
                if user_id is None:
                    q = []
                else:
                    q = M.ProjectRole.query.find(dict(user_id=user_id))
                roles = RoleCache(self, q)
            else:
                self.load_user_roles(user_id, project_id)
                roles = self.users.get((user_id, project_id))
            self.users[user_id, project_id] = roles
        return roles

    def user_has_any_role(self, user_id, project_id, role_ids):
        user_roles = self.user_roles(user_id=user_id, project_id=project_id)
        return bool(set(role_ids)  & user_roles.reaching_ids_set)

    def users_with_named_role(self, project_id, name):
        """ returns in sorted order """
        roles = self.project_roles(project_id)
        return sorted(RoleCache(self, roles.find(name=name)).users_that_reach, key=lambda u:u.username)

    def userids_with_named_role(self, project_id, name):
        roles = self.project_roles(project_id)
        return RoleCache(self, roles.find(name=name)).userids_that_reach

class RoleCache(object):

    def __init__(self, cred, q):
        self.cred = cred
        self.q = q

    def find(self, **kw):
        tests = kw.items()
        def _iter():
            for r in self:
                for k,v in tests:
                    val = getattr(r, k)
                    if callable(v):
                        if not v(val): break
                    elif v != val: break
                else:
                    yield r
        return RoleCache(self.cred, _iter())

    def get(self, **kw):
        for x in self.find(**kw): return x
        return None

    def __iter__(self):
        return self.index.itervalues()

    def __len__(self):
        return len(self.index)

    @LazyProperty
    def index(self):
        return dict((r._id, r) for r in self.q)

    @LazyProperty
    def named(self):
        return RoleCache(self.cred, (
            r for r in self
            if r.name and not r.name.startswith('*')))

    @LazyProperty
    def reverse_index(self):
        rev_index = defaultdict(list)
        for r in self:
            for rr_id in r.roles:
                rev_index[rr_id].append(r)
        return rev_index

    @LazyProperty
    def roles_that_reach(self):
        def _iter():
            visited = set()
            to_visit = list(self)
            while to_visit:
                r = to_visit.pop(0)
                if r in visited: continue
                visited.add(r)
                yield r
                pr_rindex = self.cred.project_roles(r.project_id).reverse_index
                to_visit += pr_rindex[r._id]
        return RoleCache(self.cred, _iter())

    @LazyProperty
    def users_that_reach(self):
        return [
            r.user for r in self.roles_that_reach if r.user ]

    @LazyProperty
    def userids_that_reach(self):
        return [
            r.user_id for r in self.roles_that_reach ]

    @LazyProperty
    def reaching_roles(self):
        def _iter():
            to_visit = self.index.items()
            visited = set()
            while to_visit:
                (rid, role) = to_visit.pop()
                if rid in visited: continue
                yield role
                pr_index = self.cred.project_roles(role.project_id).index
                for i in pr_index[rid].roles:
                    if i in pr_index:
                        to_visit.append((i, pr_index[i]))
        return RoleCache(self.cred, _iter())

    @LazyProperty
    def reaching_ids(self):
        return [ r._id for r in self.reaching_roles ]

    @LazyProperty
    def reaching_ids_set(self):
        return set(self.reaching_ids)

def has_access(obj, permission, user=None, project=None):
    '''Return whether the given user has the permission name on the given object.

    - First, all the roles for a user in the given project context are computed.

    - Next, for each role, the given object's ACL is examined linearly. If an ACE
      is found which matches the permission and user, and that ACE ALLOWs access,
      then the function returns True and access is permitted. If the ACE DENYs
      access, then that role is removed from further consideration.

    - If the obj is not a Neighborhood and the given user has the 'admin'
      permission on the current neighborhood, then the function returns True and
      access is allowed.

    - If none of the ACEs on the object ALLOW access, and there are no more roles
      to be considered, then the function returns False and access is denied.

    - Processing continues using the remaining roles and the
      obj.parent_security_context(). If the parent_security_context is None, then
      the function returns False and access is denied.

    The effect of this processing is that if *any* role for the user is ALLOWed
    access via a linear traversal of the ACLs, then access is allowed. All of the
    users roles must either be explicitly DENYed or processing terminate with no
    matches to DENY access to the resource.
    '''
    from allura import model as M
    def predicate(obj=obj, user=user, project=project, roles=None):
        if roles is None:
            if user is None: user = c.user
            assert user, 'c.user should always be at least M.User.anonymous()'
            cred = Credentials.get()
            if project is None:
                if isinstance(obj, M.Neighborhood):
                    project = obj.neighborhood_project
                    if project is None:
                        log.error('Neighborhood project missing for %s', obj)
                        return False
                elif isinstance(obj, M.Project):
                    project = obj.root_project
                else:
                    project = c.project.root_project
            roles = cred.user_roles(user_id=user._id, project_id=project._id).reaching_ids
        chainable_roles = []
        for rid in roles:
            for ace in obj.acl:
                if M.ACE.match(ace, rid, permission):
                    if ace.access == M.ACE.ALLOW:
                        # access is allowed
                        # log.info('%s: True', txt)
                        return True
                    else:
                        # access is denied for this role
                        break
            else:
                # access neither allowed or denied, may chain to parent context
                chainable_roles.append(rid)
        parent = obj.parent_security_context()
        if parent and chainable_roles:
            result = has_access(parent, permission, user=user, project=project)(
                roles=tuple(chainable_roles))
        elif not isinstance(obj, M.Neighborhood):
            result = has_access(project.neighborhood, 'admin', user=user)()
        else:
            result = False
        # log.info('%s: %s', txt, result)
        return result
    return TruthyCallable(predicate)

def require(predicate, message=None):
    '''
    Example: require(has_access(c.app, 'read'))

    :param callable predicate: truth function to call
    :param str message: message to show upon failure
    :raises: HTTPForbidden or HTTPUnauthorized
    '''

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

def require_access(obj, permission, **kwargs):
    predicate = has_access(obj, permission, **kwargs)
    return require(predicate, message='%s access required' % permission.capitalize())

def require_authenticated():
    '''
    :raises: HTTPUnauthorized if current user is anonymous
    '''
    from allura import model as M
    if c.user == M.User.anonymous():
        raise exc.HTTPUnauthorized()

def simple_grant(acl, role_id, permission):
    from allura.model.types import ACE
    for ace in acl:
        if ace.role_id == role_id and ace.permission == permission: return
    acl.append(ACE.allow(role_id, permission))

def simple_revoke(acl, role_id, permission):
    remove = []
    for i, ace in enumerate(acl):
        if ace.role_id == role_id and ace.permission == permission:
            remove.append(i)
    for i in reversed(remove):
        acl.pop(i)
