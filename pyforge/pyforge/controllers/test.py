# -*- coding: utf-8 -*-
"""Main Controller"""
import os
import logging
from urllib import unquote

import pkg_resources
from pylons import c, request, response
from webob import exc
from tg import expose
from tg.decorators import without_trailing_slash

import  ming.orm.ormsession

import pyforge
from pyforge.lib.base import BaseController
from pyforge.lib.security import require, require_authenticated, has_project_access, has_artifact_access
from pyforge.lib import helpers as h
from pyforge.lib import plugin
from pyforge import model as M
from .root import RootController
from .project import ProjectController
from .auth import AuthController
from .static import StaticController
from .search import SearchController
from .error import ErrorController
from .rest import RestController
from .oembed import OEmbedController

__all__ = ['RootController']

log = logging.getLogger(__name__)

class TestController(BaseController, ProjectController):
    '''Root controller for testing -- it behaves just like a
    ProjectController for test/ except that all tools are mounted,
    on-demand, at the mount point that is the same as their entry point
    name.

    Also, the test_admin is perpetually logged in here.
    '''

    def __init__(self):
        setattr(self, 'feed.rss', self.feed)
        setattr(self, 'feed.atom', self.feed)
        self.oembed = OEmbedController()
        for n in M.Neighborhood.query.find():
            if n.url_prefix.startswith('//'): continue
            n.bind_controller(self)
        proxy_root = RootController()
        self.dispatch = DispatchTest()
        self.security = SecurityTests()
        for attr in ('index', 'browse', 'markdown_to_html', 'auth', 'nf', 'error'):
            setattr(self, attr, getattr(proxy_root, attr))
        self.gsearch = proxy_root.search
        self.rest = RestController()
        super(TestController, self).__init__()

    def _setup_request(self):
        # This code fixes a race condition in our tests
        c.project = M.Project.query.get(shortname='test')
        while c.project is None:
            import sys, time
            time.sleep(0.5)
            print >> sys.stderr, 'Project "test" not found, retrying...'
            c.project = M.Project.query.get(shortname='test')

    @expose()
    def _lookup(self, name, *remainder):
        if not h.re_path_portion.match(name):
            raise exc.HTTPNotFound, name
        subproject = M.Project.query.get(shortname=c.project.shortname + '/' + name)
        if subproject:
            c.project = subproject
            c.app = None
            return ProjectController(), remainder
        app = c.project.app_instance(name)
        if app is None:
            c.project.install_app(name, name)
            app = c.project.app_instance(name)
            if app is None:
                raise exc.HTTPNotFound, name
        c.app = app
        return app.root, remainder
    # 
    # @expose('pyforge.templates.project_index')
    # def index(self):
    #     require(has_project_access('read'))
    #     return dict()

    def __call__(self, environ, start_response):
        c.app = None
        c.project = M.Project.query.get(shortname='test')
        c.user = plugin.AuthenticationProvider.get(request).by_username(
            environ.get('username', 'test_admin'))
        return BaseController.__call__(self, environ, start_response)

class DispatchTest(object):

    @expose()
    def _lookup(self, *args):
        if args:
            return NamedController(args[0]), args[1:]
        else:
            raise exc.HTTPNotFound()

class NamedController(object):

    def __init__(self, name):
        self.name = name

    @expose()
    def index(self):
        return 'index ' + self.name

    @expose()
    def _default(self, *args):
        return 'default(%s)(%r)' % (self.name, args)

class SecurityTests(object):

    @expose()
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

