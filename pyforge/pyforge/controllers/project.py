from urllib import unquote
from mimetypes import guess_type
import Image
import os

from tg import expose, flash, redirect, validate, request, response
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import c, g
from webob import exc
from pymongo.bson import ObjectId
from formencode import validators

import  ming.orm.ormsession

import pyforge
from pyforge import model as M
from pyforge.app import SitemapEntry
from pyforge.lib.base import BaseController
from pyforge.lib.helpers import vardec, DateTimeConverter
from pyforge.controllers.error import ErrorController
from pyforge.lib.security import require, has_project_access, has_neighborhood_access
from pyforge.lib.widgets import form_fields as ffw
from pyforge.lib.widgets import project_list as plw
from .auth import AuthController
from .search import SearchController, ProjectBrowseController
from .static import StaticController

from mako.template import Template
from pyforge.model.session import main_orm_session

CACHED_CSS = dict()

class W:
    markdown_editor = ffw.MarkdownEdit()
    project_summary = plw.ProjectSummary()

class NeighborhoodController(object):
    '''Manages a neighborhood of projects.
    '''

    def __init__(self, neighborhood_name, prefix=''):
        self.neighborhood_name = neighborhood_name
        self.neighborhood = M.Neighborhood.query.get(name=self.neighborhood_name)
        self.prefix = prefix
        self.browse = NeighborhoodProjectBrowseController(neighborhood=self.neighborhood)
        self._admin = NeighborhoodAdminController(self.neighborhood)
        self._moderate = NeighborhoodModerateController(self.neighborhood)
    
    def _check_security(self):
        require(has_neighborhood_access('read', self.neighborhood),
                'Read access required')

    @expose()
    def _lookup(self, pname, *remainder):
        pname = unquote(pname)
        project = M.Project.query.get(shortname=self.prefix + pname)
        if project is None:
            raise exc.HTTPNotFound, pname
        if project.neighborhood.name != self.neighborhood_name:
            redirect(project.url())
        c.project = project
        return ProjectController(), remainder

    @expose('pyforge.templates.neighborhood_project_list')
    def index(self):
        c.project_summary = W.project_summary
        projects = M.Project.query.find(dict(neighborhood_id=self.neighborhood._id)).sort('name').all()
        categories = M.ProjectCategory.query.find({'parent_id':None}).sort('name').all()
        c.custom_sidebar_menu = [SitemapEntry('Categories')] + [
            SitemapEntry(cat.label, self.neighborhood.url()+'browse/'+cat.name, className='nav_child') for cat in categories
        ]
        return dict(neighborhood=self.neighborhood,
                    title="Welcome to "+self.neighborhood.name,
                    text=g.markdown.convert(self.neighborhood.homepage),
                    projects=projects)

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

    @expose()
    def icon(self):
        with self.neighborhood.icon.open() as fp:
            filename = fp.metadata['filename']
            response.headers['Content-Type'] = ''
            response.content_type = fp.content_type
            response.headers.add('Content-Disposition',
                                     'attachment;filename=%s' % filename)
            return fp.read()
        return self.neighborhood.icon.filename

    @expose()
    @without_trailing_slash
    def site_style(self):
        """Display the css for the default theme."""
        if self.neighborhood._id in CACHED_CSS:
            css = CACHED_CSS[self.neighborhood._id]
        else:
            theme = M.Theme.query.find(dict(neighborhood_id=self.neighborhood._id)).first()
            if theme == None:
                theme = M.Theme.query.find(dict(name='forge_default')).first()
            
            template_path = os.path.join(pyforge.__path__[0],'templates')
            file_path = os.path.join(template_path,'style.mak')
            colors = dict(color1=theme.color1,
                          color2=theme.color2,
                          color3=theme.color3,
                          color4=theme.color4)
            css = Template(filename=file_path, module_directory=template_path).render(**colors)
            if self.neighborhood.css:
                css = css + Template(self.neighborhood.css).render(**colors)
            CACHED_CSS[self.neighborhood._id] = css
        response.headers['Content-Type'] = ''
        response.content_type = 'text/css'
        return css

class NeighborhoodProjectBrowseController(ProjectBrowseController):
    def __init__(self, neighborhood=None, category_name=None, parent_category=None):
        self.neighborhood = neighborhood
        super(NeighborhoodProjectBrowseController, self).__init__(category_name=category_name, parent_category=parent_category)
        self.nav_stub = '%sbrowse/' % self.neighborhood.url()
        self.additional_filters = {'neighborhood_id':self.neighborhood._id}

    @expose()
    def _lookup(self, category_name, *remainder):
        return NeighborhoodProjectBrowseController(neighborhood=self.neighborhood, category_name=category_name, parent_category=self.category), remainder

    @expose('pyforge.templates.neighborhood_project_list')
    @without_trailing_slash
    def index(self):
        c.project_summary = W.project_summary
        projects = self._find_projects()
        title=self._build_title()
        c.custom_sidebar_menu = self._build_nav()
        return dict(projects=projects,
                    title=title,
                    text=None,
                    neighborhood=self.neighborhood)

class HostNeighborhoodController(BaseController, NeighborhoodController):
    '''Neighborhood controller with support for use as a root controller, for
    instance, when using adobe.sourceforge.net (if this is allowed).
    '''

    auth = AuthController()
    error = ErrorController()
    static = StaticController()
    search = SearchController()

class ProjectController(object):

    def __init__(self):
        setattr(self, 'feed.rss', self.feed)
        setattr(self, 'feed.atom', self.feed)
        self.screenshot = ScreenshotsController()

    @expose()
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
    def feed(self, since=None, until=None, offset=None, limit=None):
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

    @expose()
    def icon(self):
        with c.project.icon.open() as fp:
            filename = fp.metadata['filename']
            response.headers['Content-Type'] = ''
            response.content_type = fp.content_type
            response.headers.add('Content-Disposition',
                                     'attachment;filename=%s' % filename)
            return fp.read()
        return c.project.icon.filename

class ScreenshotsController(object):

    @expose()
    def _lookup(self, filename, *args):
        return ScreenshotController(filename), args

class ScreenshotController(object):

    def __init__(self, filename):
        self.filename = filename

    @expose()
    def index(self, embed=False):
        screenshot = M.ProjectFile.query.find({'metadata.project_id':c.project._id, 'metadata.category':'screenshot', 'filename':self.filename}).first()
        with screenshot.open() as fp:
            filename = fp.metadata['filename']
            response.headers['Content-Type'] = ''
            response.content_type = fp.content_type
            if not embed:
                response.headers.add('Content-Disposition',
                                     'attachment;filename=%s' % filename)
            return fp.read()
        return self.filename

    @expose()
    def thumb(self, embed=False):
        thumb = M.ProjectFile.query.find({'metadata.project_id':c.project._id, 'metadata.category':'screenshot_thumb', 'metadata.filename':self.filename}).first()
        with thumb.open() as fp:
            filename = fp.metadata['filename']
            response.headers['Content-Type'] = ''
            response.content_type = fp.content_type
            if not embed:
                response.headers.add('Content-Disposition',
                                     'attachment;filename=%s' % filename)
            return fp.read()
        return self.filename

class NeighborhoodAdminController(object):

    def __init__(self, neighborhood):
        self.neighborhood = neighborhood
        self.awards = NeighborhoodAwardsController(self.neighborhood)

    def _check_security(self):
        require(has_neighborhood_access('admin', self.neighborhood),
                'Admin access required')

    @expose('pyforge.templates.neighborhood_admin')
    def index(self):
        c.markdown_editor = W.markdown_editor
        psort = [(n, M.Project.query.find(dict(is_root=True, neighborhood_id=n._id)).all())
                 for n in M.Neighborhood.query.find().sort('name')]
#        accolades = M.AwardGrant.query.find(dict(granted_to_project_id=c.project._id))
        awards = M.Award.query.find(dict(created_by_neighborhood_id=self.neighborhood._id))
        awards_count = len(awards)
        assigns = M.Award.query.find(dict(created_by_neighborhood_id=self.neighborhood._id))
        assigns_count = len(assigns)
        grants = M.AwardGrant.query.find(dict(granted_by_neighborhood_id=self.neighborhood._id))
        grants_count = len(grants)
        return dict(
            projects=psort,
#            accolades=accolades,
            awards=awards,
            awards_count=awards_count,
            assigns=assigns,
            assigns_count=assigns_count,
            grants=grants,
            grants_count=grants_count,
            neighborhood=self.neighborhood)

    @expose()
    def update(self, name=None, css=None, homepage=None, icon=None,
               color1=None, color2=None, color3=None, color4=None):
        self.neighborhood.name = name
        self.neighborhood.homepage = homepage
        self.neighborhood.css = css
        if css and self.neighborhood._id in CACHED_CSS:
            del CACHED_CSS[self.neighborhood._id]
        if color1 or color2 or color3 or color4:
            if self.neighborhood._id in CACHED_CSS:
                del CACHED_CSS[self.neighborhood._id]
            if not self.neighborhood.theme:
                theme = M.Theme(neighborhood_id=self.neighborhood._id)
            else:
                theme = self.neighborhood.theme
            theme.color1 = color1
            theme.color2 = color2
            theme.color3 = color3
            theme.color4 = color4
        if icon is not None and icon != '' and 'image/' in icon.type:
            filename = icon.filename
            if icon.type: content_type = icon.type
            else: content_type = 'application/octet-stream'
            image = Image.open(icon.file)
            format = image.format
            if image.size[0] < image.size[1]:
                h_offset = (image.size[1]-image.size[0])/2
                image = image.crop((0, h_offset, image.size[0], image.size[0]+h_offset))
            elif image.size[0] > image.size[1]:
                w_offset = (image.size[0]-image.size[1])/2
                image = image.crop((w_offset, 0, image.size[1]+w_offset, image.size[1]))
            image.thumbnail((48, 48), Image.ANTIALIAS)
            if self.neighborhood.icon:
                M.NeighborhoodFile.query.remove({'metadata.neighborhood_id':self.neighborhood._id})
            with M.NeighborhoodFile.create(
                content_type=content_type,
                filename=filename,
                neighborhood_id=self.neighborhood._id) as fp:
                image.save(fp, format)
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

class NeighborhoodAwardsController(object):

    def __init__(self, neighborhood=None):
        if neighborhood is not None:
            self.neighborhood = neighborhood

    @expose('pyforge.templates.awards')
    def index(self, **kw):
        awards = M.Award.query.find(dict(created_by_neighborhood_id=self.neighborhood._id))
        count=0
        count = len(awards)
        return dict(awards=awards or [], count=count)

    @expose('pyforge.templates.grants')
    def grants(self, **kw):
        grants = M.AwardGrant.query.find(dict(granted_by_neighborhood_id=self.neighborhood._id))
        count=0
        count = len(grants)
        return dict(grants=grants or [], count=count)

    @expose()
    def award_save(self, short=None, full=None, **post_data):
        if request.method != 'POST':
            raise Exception('award_save must be a POST request')
        app_config_id = ObjectId()
        plugin_verson = { 'neighborhood':'0' }
        award = M.Award(app_config_id=app_config_id, plugin_verson=plugin_verson)
        award.short = short
        award.full = full
        award.created_by_neighborhood_id = self.neighborhood._id
        # may want to have auxiliary data fields
        for k,v in post_data.iteritems():
            setattr(award, k, v)
        redirect(request.referer)

    @expose()
    def award_grant(self, grant=None, recipient=None):
        if request.method != 'POST':
            raise Exception('award_grant must be a POST request')
        grant_q = M.Award.query.find(dict(short=grant)).first()
        recipient_q = M.Project.query.find(dict(name=recipient)).first()
        app_config_id = ObjectId()
        plugin_verson = { 'neighborhood':'0' }
        award = M.AwardGrant(app_config_id=app_config_id, plugin_verson=plugin_verson)
        award.award_id = grant_q._id
        award.granted_to_project_id = recipient_q._id
        award.granted_by_neighborhood_id = self.neighborhood._id
#        award.app_config_id = c.app.config._id
        redirect(request.referer)

    @expose()
    def award_delete(self, award_id=None):
        aid = ObjectId(award_id)
        award = M.Award.query.find(dict(_id=aid)).first()
        if award:
            grants = M.AwardGrant.query.find(dict(award_id=award._id))
            for grant in grants:
                grant.delete()
            award.delete()
        redirect(request.referer)

    @expose()
    def grant_delete(self, grant_id=None):
        gid = ObjectId(grant_id)
        grant = M.AwardGrant.query.find(dict(_id=gid)).first()
        grant.delete()
        redirect(request.referer)

