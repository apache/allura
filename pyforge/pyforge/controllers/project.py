from tg import expose, flash, redirect
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import c
from webob import exc

from pyforge import model as M
from pyforge.lib.base import BaseController
from pyforge.controllers.error import ErrorController
from pyforge.lib.dispatch import _dispatch
from pyforge.lib.security import require, require_authenticated, has_project_access
from .auth import AuthController
from .search import SearchController
from .static import StaticController


class ProjectsController(object):

    def __init__(self, prefix):
        self.prefix = prefix
    
    def _lookup(self, pname, *remainder):
        project = M.Project.query.get(_id=self.prefix + pname + '/')
        if project is None:
            raise exc.HTTPNotFound, pname
        c.project = project
        return ProjectController(), remainder

    @expose()
    def register(self, pid):
        require_authenticated()
        try:
            p = c.user.register_project(pid)
        except Exception, ex:
            flash('%s: %s' % (ex.__class__, str(ex)), 'error')
            redirect('/')
        redirect(p.script_name + 'admin/')

class ProjectController(object):

    def _lookup(self, name, *remainder):
        subproject = M.Project.query.get(_id=c.project._id + name + '/')
        if subproject:
            c.project = subproject
            c.app = None
            return ProjectController(), remainder
        app = c.project.app_instance(name)
        if app is None:
            raise exc.HTTPNotFound, name
        c.app = app
        return app.root, remainder

    def _check_security(self):
        require(has_project_access('read'),
                'Read access required')

    @expose()
    @with_trailing_slash
    def index(self):
        redirect('home/')

    @expose('pyforge.templates.project_sitemap')
    @without_trailing_slash
    def sitemap(self):
        require(has_project_access('read'))
        return dict()

class HostProjectController(BaseController, ProjectController):

    auth = AuthController()
    error = ErrorController()
    static = StaticController()
    search = SearchController()

    def __init__(self, project):
        c.project = project

    def _lookup(self, name, *remainder):
        subproject = M.Project.query.get(_id=c.project._id + name + '/')
        if subproject:
            c.project = subproject
            c.app = None
            return ProjectController(), remainder
        app = c.project.app_instance(name)
        if app is None:
            raise exc.HTTPNotFound, name
        c.app = app
        return app.root, remainder

    def _check_security(self):
        require(has_project_access('read'),
                'Read access required')

    @expose()
    @with_trailing_slash
    def index(self):
        redirect('home/')

    @expose('pyforge.templates.project_sitemap')
    @without_trailing_slash
    def sitemap(self):
        require(has_project_access('read'))
        return dict()
    
    def _dispatch(self, state, remainder):
        return _dispatch(self, state, remainder)
        
