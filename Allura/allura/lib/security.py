"""
This module provides the security predicates used in decorating various models.
"""
from collections import defaultdict

from pylons import c, request
from webob import exc
from itertools import chain
from ming.utils import LazyProperty

class Credentials(object):

    def __init__(self):
        self.clear()

    @classmethod
    def get(cls):
        import allura
        return allura.credentials

    def clear(self):
        self.users = {}
        self.projects = {}

    def project_roles(self, project_id):
        from allura import model as M
        roles = self.projects.get(project_id)
        if roles is None:
            roles = self.projects[project_id] = RoleCache(
                self,  M.ProjectRole.query.find(dict(project_id=project_id)))
        return roles

    def user_roles(self, user_id, project_id=None):
        from allura import model as M
        roles = self.users.get((user_id, project_id))
        if roles is None:
            if project_id is None:
                if user_id is None:
                    q = []
                else:
                    q = M.ProjectRole.query.find(dict(user_id=user_id))
            else:
                if user_id is None:
                    q = M.ProjectRole.query.find(
                        dict(project_id=project_id,name='*anonymous'))
                else:
                    q0 = M.ProjectRole.query.find(
                        dict(project_id=project_id,
                             name={'$in':['*anonymous', '*authenticated']}))
                    q1 = M.ProjectRole.query.find(
                        dict(project_id=project_id, user_id=user_id))
                    q = chain(q0, q1)
            self.users[user_id, project_id] = roles = RoleCache(self, q)
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
            r.user for r in self.roles_that_reach if r.user_id is not None ]

    @LazyProperty
    def userids_that_reach(self):
        return [
            r.user_id for r in self.roles_that_reach if r.user_id is not None ]

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
        cred = Credentials.get()
        for proj in project.parent_iter():
            acl = set(proj.acl.get(access_type, []))
            if cred.user_has_any_role(user._id, project.root_project._id, acl): return True
        if has_neighborhood_access('admin', project.neighborhood, user)():
            return True
        return False
    return result

def has_artifact_access(access_type, obj=None, user=None, app=None):
    def result(user=user, app=app):
        if user is None: user = c.user
        if app is None: app = c.app
        project_id = app.project.root_project._id
        assert user, 'c.user should always be at least M.User.anonymous()'
        cred = Credentials.get()
        acl = set(app.config.acl.get(access_type, []))
        if obj is not None:
            acl |= set(obj.acl.get(access_type, []))
        if cred.user_has_any_role(user._id, project_id, acl): return True
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
