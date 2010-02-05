# -*- coding: utf-8 -*-
"""Main Controller"""
import logging
from urllib import unquote

import pkg_resources
from pylons import c
from webob import exc
from tg import expose

import  ming.orm.ormsession

from pyforge.lib.base import BaseController
from pyforge.lib.dispatch import _dispatch, default
from pyforge.lib.security import require, require_authenticated, has_project_access, has_artifact_access
from pyforge import model as M
from .project import ProjectController
from .auth import AuthController
from .static import StaticController
from .search import SearchController
from .error import ErrorController
from .oembed import OEmbedController

__all__ = ['RootController']

log = logging.getLogger(__name__)

class TestController(BaseController, ProjectController):
    '''Root controller for testing -- it behaves just like a
    ProjectController for test/ except that all plugins are mounted,
    on-demand, at the mount point that is the same as their entry point
    name.

    Also, the test_admin is perpetually logged in here.
    '''

    def __init__(self):
        c.project = M.Project.query.get(shortname='test')
        self.dispatch = DispatchTest()
        self.security = SecurityTests()
        self.auth = AuthController()
        self.static = StaticController()
        self.gsearch = SearchController()
        self.error = ErrorController()
        self.oembed = OEmbedController()
        for n in M.Neighborhood.query.find():
            if n.url_prefix.startswith('//'): continue
            n.bind_controller(self)

    def _dispatch(self, state, remainder):
        return _dispatch(self, state, remainder)
        
    def _lookup(self, name, *remainder):
        subproject = M.Project.query.get(shortname=c.project.shortname + '/' + name)
        if subproject:
            c.project = subproject
            c.app = None
            return ProjectController(), remainder
        app = c.project.app_instance(name)
        app = c.project.app_instance(name)
        if app is None:
            c.project.install_app(name, name)
            app = c.project.app_instance(name)
            if app is None:
                raise exc.HTTPNotFound, name
        c.app = app
        return app.root, remainder

    @expose('pyforge.templates.project_index')
    def index(self):
        require(has_project_access('read'))
        return dict()

    def __call__(self, environ, start_response):
        c.app = None
        c.project = M.Project.query.get(shortname='test')
        c.user = M.User.query.get(username=environ.get('username', 'test_admin'))
        app = lambda e,s: BaseController.__call__(self, e, s)
        try:
            result = app(environ, start_response)
            if not isinstance(result, list):
                return self._cleanup_iterator(result)
            else:
                self._cleanup_request()
                return result
        except exc.HTTPRedirection:
            self._cleanup_request()
            raise
        except:
            ming.orm.ormsession.ThreadLocalORMSession.close_all()
            raise

    def _cleanup_iterator(self, result):
        for x in result:
            yield x
        self._cleanup_request()

    def _cleanup_request(self):
        ming.orm.ormsession.ThreadLocalORMSession.flush_all()
        ming.orm.ormsession.ThreadLocalORMSession.close_all()

class DispatchTest(object):

    def _lookup(self, name, *args):
        return NamedController(name), args

class NamedController(object):

    def __init__(self, name):
        self.name = name

    @expose()
    def index(self):
        return 'index ' + self.name

    @default
    @expose()
    def _lookup(self, *args):
        return 'default(%s)(%r)' % (self.name, args)

class SecurityTests(object):

    def _lookup(self, name, *args):
        name = unquote(name)
        if name == '*anonymous':
            c.user = M.User.anonymous()
        return SecurityTest(), args

class SecurityTest(object):

    def __init__(self):
        from helloforge import model as HM
        self.page = HM.Page.query.get(title='Root')
        c.app = c.project.app_instance('hello')

    @expose()
    def forbidden(self):
        require(lambda:False, 'Never allowed')
        return ''

    @expose()
    def needs_auth(self):
        require_authenticated()
        return ''

    @expose()
    def needs_project_access_fail(self):
        require(has_project_access('no_such_permission'))
        return ''

    @expose()
    def needs_project_access_ok(self):
        pred = has_project_access('read')
        if not pred():
            print 'Inside needs_project_access, c.user = %s' % c.user
            import pdb; pdb.set_trace()
        require(pred)
        return ''

    @expose()
    def needs_artifact_access_fail(self):
        require(has_artifact_access('no_such_permission', self.page))
        return ''

    @expose()
    def needs_artifact_access_ok(self):
        require(has_artifact_access('read', self.page))
        return ''

