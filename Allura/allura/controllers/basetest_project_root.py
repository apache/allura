#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

"""Main Controller"""
import logging
from six.moves.urllib.parse import unquote

from tg import tmpl_context as c
from tg import request
from webob import exc
from tg import expose
from tg import TGController
from paste.deploy.converters import asbool

from allura.lib.security import require, require_authenticated, require_access, has_access
from allura.lib import helpers as h
from allura.lib import plugin
from allura import model as M
from .root import RootController
from .project import ProjectController
from .rest import RestController

__all__ = ['RootController']

log = logging.getLogger(__name__)


class BasetestProjectRootController(TGController, ProjectController):
    '''Root controller for testing -- it behaves just like the RootController
    plus acts as shorthand for the ProjectController at /p/test/ plus all tools are mounted,
    on-demand, at the mount point that is the same as their entry point name.

    Also, the test-admin is perpetually logged in here.

    The name of this controller is dictated by the override_root setting
    in development.ini and the magical import rules of TurboGears.  The
    override_root setting has to match the name of this file, which has
    to match (less underscores, case changes, and the addition of
    "Controller") the name of this class.  It will then be registered
    as the root controller instead of allura.controllers.root.RootController.
    '''

    def __init__(self):
        self.p_nbhd = M.Neighborhood.query.get(url_prefix='/p/')
        assert self.p_nbhd

        self.dispatch = DispatchTest()
        self.security = SecurityTests()

        # proxy root controller paths
        self.real_root_controller = RootController()
        for attr in dir(self.real_root_controller):
            if not attr.startswith('_'):
                setattr(self, attr, getattr(self.real_root_controller, attr))

        # neighborhoods & projects handled in _lookup

        super().__init__()

    @expose()
    def _lookup(self, name, *remainder):
        # first try a neighborhood path through the real root controller
        try:
            return self.real_root_controller._lookup(name, *remainder)
        except exc.HTTPNotFound:
            pass

        # magic shorthand helper lookups so self.app.get('/wiki') instantiates a wiki and calls /p/test/wiki controller

        subproject = M.Project.query.get(
            shortname=c.project.shortname + '/' + name,
            neighborhood_id=self.p_nbhd._id)
        if subproject:
            c.project = subproject
            c.app = None
            return ProjectController(), remainder
        app = c.project.app_instance(name)
        if app is None:
            prefix = 'test-app-'
            ep_name = name
            if name.startswith('test-app-'):
                ep_name = name[len(prefix):]
            try:
                c.project.install_app(ep_name, name)
            except KeyError:
                raise exc.HTTPNotFound(name)
            app = c.project.app_instance(name)
            if app is None:
                raise exc.HTTPNotFound(name)
        c.app = app
        return app.root, remainder

    def _perform_call(self, context):
        """ Called from a WebTest 'app' instance, going through TurboGears dispatcher code
        Example: self.app.get('/auth/', extra_environ={'disable_auth_magic': "True"})
        """
        environ = context.request.environ
        c.app = None
        c.project = M.Project.query.get(
            shortname='test', neighborhood_id=self.p_nbhd._id)
        auth = plugin.AuthenticationProvider.get(request)
        if not asbool(environ.get('disable_auth_magic')):
            user = auth.by_username(environ.get('username', 'test-admin'))
            if not user:
                user = M.User.anonymous()
            environ['beaker.session']['username'] = user.username
            # save and persist, so that a creation time is set
            environ['beaker.session'].save()
            environ['beaker.session'].persist()
        c.user = auth.authenticate_request()
        return super()._perform_call(context)


class DispatchTest:
    @expose()
    def _lookup(self, *args):
        if args:
            return NamedController(args[0]), args[1:]
        else:
            raise exc.HTTPNotFound()


class NamedController:
    def __init__(self, name):
        self.name = name

    @expose()
    def index(self, **kw):
        return 'index ' + self.name

    @expose()
    def _default(self, *args):
        return f'default({self.name})({args!r})'


class SecurityTests:
    @expose()
    def _lookup(self, name, *args):
        name = unquote(name)
        if name == '*anonymous':
            c.user = M.User.anonymous()
        return SecurityTest(), args


class SecurityTest:
    def __init__(self):
        from forgewiki import model as WM
        c.app = c.project.app_instance('wiki')
        self.page = WM.Page.query.get(
            app_config_id=c.app.config._id, title='Home')

    @expose()
    def forbidden(self):
        require(lambda: False, 'Never allowed')
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
