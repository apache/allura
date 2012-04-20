# -*- coding: utf-8 -*-
"""Main Controller"""
import os
import logging
from urllib import unquote

import pkg_resources
from pylons import c, g, request, response
from webob import exc
from tg import expose, redirect
from tg.decorators import without_trailing_slash

import  ming.orm.ormsession

import allura
from allura.lib.base import WsgiDispatchController
from allura.lib.security import require, require_authenticated, require_access, has_access
from allura.lib import helpers as h
from allura.lib import plugin
from allura import model as M
from .root import RootController
from .project import NeighborhoodController, ProjectController
from .auth import AuthController
from .static import NewForgeController
from .search import SearchController
from .error import ErrorController
from .rest import RestController

__all__ = ['RootController']

log = logging.getLogger(__name__)

class TestNeighborhoodRootController(WsgiDispatchController, NeighborhoodController):
    '''Root controller for testing -- it behaves just like a
    NeighborhoodController for test/ except that all tools are mounted,
    on-demand, at the mount point that is the same as their entry point
    name.

    Also, the test-admin is perpetually logged in here.

    The name of this controller is dictated by the override_root setting
    in development.ini and the magical import rules of TurboGears.  The
    override_root setting has to match the name of this file, which has
    to match (less underscores, case changes, and the addition of
    "Controller") the name of this class.  It will then be registered
    as the root controller instead of allura.controllers.root.RootController.
    '''

    def __init__(self):
        for n in M.Neighborhood.query.find():
            if n.url_prefix.startswith('//'): continue
            n.bind_controller(self)
        self.p_nbhd = M.Neighborhood.query.get(name='Projects')
        proxy_root = RootController()
        self.dispatch = DispatchTest()
        self.security = SecurityTests()
        for attr in ('index', 'browse', 'auth', 'nf', 'error'):
            setattr(self, attr, getattr(proxy_root, attr))
        self.gsearch = proxy_root.search
        self.rest = RestController()
        super(TestNeighborhoodRootController, self).__init__()

    def _setup_request(self):
        pass

    def _cleanup_request(self):
        pass

    @expose()
    def _lookup(self, pname, *remainder):
        pname = unquote(pname)
        if not h.re_path_portion.match(pname):
            raise exc.HTTPNotFound, pname
        project = M.Project.query.get(shortname=self.prefix + pname, neighborhood_id=self.neighborhood._id)
        if project is None:
            project = self.neighborhood.neighborhood_project
            c.project = project
            return ProjectController()._lookup(pname, *remainder)
        if project.database_configured == False:
            if remainder == ('user_icon',):
                redirect(g.forge_static('images/user.png'))
            elif c.user.username == pname:
                log.info('Configuring %s database for access to %r',
                         pname, remainder)
                project.configure_project(is_user_project=True)
            else:
                raise exc.HTTPNotFound, pname
        c.project = project
        if project is None or (project.deleted and not has_access(c.project, 'update')()):
            raise exc.HTTPNotFound, pname
        if project.neighborhood.name != self.neighborhood_name:
            redirect(project.url())
        return ProjectController(), remainder

    def __call__(self, environ, start_response):
        c.app = None
        c.user = plugin.AuthenticationProvider.get(request).by_username(
            environ.get('username', 'test-admin'))
        return WsgiDispatchController.__call__(self, environ, start_response)

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
    def index(self, **kw):
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
        from forgewiki import model as WM
        c.app = c.project.app_instance('wiki')
        self.page = WM.Page.query.get(app_config_id=c.app.config._id, title='Home')

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
        require_access(c.project, 'no_such_permission')
        return ''

    @expose()
    def needs_project_access_ok(self):
        pred = has_access(c.project, 'read')
        if not pred():
            log.info('Inside needs_project_access, c.user = %s' % c.user)
        require(pred)
        return ''

    @expose()
    def needs_artifact_access_fail(self):
        require_access(self.page, 'no_such_permission')
        return ''

    @expose()
    def needs_artifact_access_ok(self):
        require_access(self.page, 'read')
        return ''
