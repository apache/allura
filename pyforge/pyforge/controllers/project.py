from urllib import unquote

from tg import expose, flash, redirect, validate, request, response
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import c
from webob import exc
from pymongo.bson import ObjectId
from formencode import validators

import  ming.orm.ormsession

from pyforge import model as M
from pyforge.lib.base import BaseController
from pyforge.lib.helpers import vardec, DateTimeConverter
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
        self.neighborhood = M.Neighborhood.query.get(name=self.neighborhood_name)
        self.prefix = prefix
        self._admin = NeighborhoodAdminController(self.neighborhood)
        self._moderate = NeighborhoodModerateController(self.neighborhood)
    
    def _check_security(self):
        require(has_neighborhood_access('read', self.neighborhood),
                'Read access required')

    def _lookup(self, pname, *remainder):
        pname = unquote(pname)
        project = M.Project.query.get(shortname=self.prefix + pname)
        if project is None:
            raise exc.HTTPNotFound, pname
        if project.neighborhood.name != self.neighborhood_name:
            redirect(project.url())
        c.project = project
        return ProjectController(), remainder

    @expose('pyforge.templates.neighborhood')
    def index(self):
        return dict(neighborhood=self.neighborhood)

    @expose()
    def register(self, pid):
        require(has_neighborhood_access('create', self.neighborhood), 'Create access required')
        try:
            p = self.neighborhood.register_project(pid)
        except Exception, ex:
            c.project = None
            ming.orm.ormsession.ThreadLocalORMSession.close_all()
            flash('%s: %s' % (ex.__class__, str(ex)), 'error')
            redirect('.')
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

    def __init__(self):
        setattr(self, 'feed.rss', self.feed)
        setattr(self, 'feed.atom', self.feed)

    def _lookup(self, name, *remainder):
        name=unquote(name)
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
        if c.project.shortname.startswith('users/'):
            redirect('profile/')
        else:
            redirect('home/')

    @expose('pyforge.templates.project_sitemap')
    @without_trailing_slash
    def sitemap(self): # pragma no cover
        raise NotImplementedError, 'sitemap'
        require(has_project_access('read'))
        return dict()

    @without_trailing_slash
    @expose()
    @validate(dict(
            since=DateTimeConverter(if_empty=None),
            until=DateTimeConverter(if_empty=None),
            offset=validators.Int(if_empty=None),
            limit=validators.Int(if_empty=None)))
    def feed(self, since, until, offset, limit):
        if request.environ['PATH_INFO'].endswith('.atom'):
            feed_type = 'atom'
        else:
            feed_type = 'rss'
        title = 'Recent changes to Project %s' % c.project.name
        feed = M.Feed.feed(
            {'artifact_reference.project_id':c.project._id},
            feed_type,
            title,
            c.project.url(),
            title,
            since, until, offset, limit)
        response.headers['Content-Type'] = ''
        response.content_type = 'application/xml'
        return feed.writeString('utf-8')

class NeighborhoodAdminController(object):

    def __init__(self, neighborhood):
        self.neighborhood = neighborhood

    def _check_security(self):
        require(has_neighborhood_access('admin', self.neighborhood),
                'Admin access required')

    @expose('pyforge.templates.neighborhood_admin')
    def index(self):
        return dict(neighborhood=self.neighborhood)

    @expose()
    def update(self, name=None, css=None, homepage=None):
        self.name = name
        self.neighborhood.css = css
        self.neighborhood.homepage = homepage
        redirect('.')

    @vardec
    @expose()
    def update_acl(self, permission=None, user=None, new=None, **kw):
        if user is None: user = []
        for u in user:
            if u.get('delete'):
                if u['id']:
                    self.neighborhood.acl[permission].remove(ObjectId(str(u['id'])))
                else:
                    self.neighborhood.acl[permission].remove(None)
        if new.get('add'):
            u = M.User.query.get(username=new['username'])
            self.neighborhood.acl[permission].append(u._id)
        redirect('.#acl-admin')

class NeighborhoodModerateController(object):

    def __init__(self, neighborhood):
        self.neighborhood = neighborhood

    def _check_security(self):
        require(has_neighborhood_access('moderate', self.neighborhood),
                'Moderator access required')

    @expose('pyforge.templates.neighborhood_moderate')
    def index(self):
        return dict(neighborhood=self.neighborhood)

    @expose()
    def invite(self, pid, invite=None, uninvite=None):
        p = M.Project.query.get(shortname=pid)
        if p is None:
            flash("Can't find %s" % pid, 'error')
            redirect('.')
        if p.neighborhood == self.neighborhood:
            flash("%s is already in the neighborhood" % pid, 'error')
            redirect('.')
        if invite:
            if self.neighborhood._id in p.neighborhood_invitations:
                flash("%s is already invited" % pid, 'warning')
                redirect('.')
            p.neighborhood_invitations.append(self.neighborhood._id)
            flash('%s invited' % pid)
        elif uninvite:
            if self.neighborhood._id not in p.neighborhood_invitations:
                flash("%s is already uninvited" % pid, 'warning')
                redirect('.')
            p.neighborhood_invitations.remove(self.neighborhood._id)
            flash('%s uninvited' % pid)
        redirect('.')

    @expose()
    def evict(self, pid):
        p = M.Project.query.get(shortname=pid, neighborhood_id=self.neighborhood._id)
        if p is None:
            flash("Cannot evict  %s; it's not in the neighborhood"
                  % pid, 'error')
            redirect('.')
        if not p.is_root:
            flash("Cannot evict %s; it's a subproject" % pid, 'error')
            redirect('.')
        n = M.Neighborhood.query.get(name='Projects')
        p.neighborhood_id = n._id
        if self.neighborhood._id in p.neighborhood_invitations:
            p.neighborhood_invitations.remove(self.neighborhood._id)
        flash('%s evicted to Projects' % pid)
        redirect('.')

