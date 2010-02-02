from tg import expose, flash, redirect
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import c
from webob import exc

from pyforge import model as M
from pyforge.lib.base import BaseController
from pyforge.controllers.error import ErrorController
from pyforge.lib.dispatch import _dispatch
from pyforge.lib.security import require, has_project_access, has_neighborhood_access
from .auth import AuthController
from .search import SearchController
from .static import StaticController

class NeighborhoodController(object):
    '''Manages a neighborhood of projects.
    '''

    def __init__(self, neighborhood_name, prefix=''):
        self.neighborhood_name = neighborhood_name
        self.prefix = prefix
    
    def _check_security(self):
        require(has_neighborhood_access('read', self.neighborhood),
                'Read access required')

    def _lookup(self, pname, *remainder):
        project = M.Project.query.get(shortname=self.prefix + pname)
        if project.neighborhood.name != self.neighborhood_name:
            redirect(project.url())
        if project is None:
            raise exc.HTTPNotFound, pname
        c.project = project
        return ProjectController(), remainder

    @property
    def neighborhood(self):
        return M.Neighborhood.query.get(name=self.neighborhood_name)

    @expose()
    def register(self, pid):
        require(has_neighborhood_access('create'), 'Create access required')
        try:
            p = self.neighborhood.register_project(pid)
        except Exception, ex:
            flash('%s: %s' % (ex.__class__, str(ex)), 'error')
            redirect('/')
        redirect(p.script_name + 'admin/')

class HostNeighborhoodController(BaseController, NeighborhoodController):
    '''Neighborhood controller with support for use as a root controller, for
    instance, when using adobe.sourceforge.net (if this is allowed).
    '''

    auth = AuthController()
    error = ErrorController()
    static = StaticController()
    search = SearchController()

    def _dispatch(self, state, remainder):
        return _dispatch(self, state, remainder)

class ProjectController(object):

    def _lookup(self, name, *remainder):
        subproject = M.Project.query.get(shortname=c.project.shortname + '/' + name)
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

