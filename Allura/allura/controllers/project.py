from urllib import unquote
from mimetypes import guess_type
import Image
import os, re

import pkg_resources
import genshi.template
from tg import expose, flash, redirect, validate, request, response
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import c, g
from webob import exc
from pymongo.bson import ObjectId
import pymongo
from formencode import validators

import  ming.orm.ormsession

import allura
from allura import model as M
from allura.app import SitemapEntry
from allura.lib.base import BaseController
from allura.lib import helpers as h
from allura.controllers.error import ErrorController
from allura.lib.security import require, has_project_access, has_neighborhood_access, has_artifact_access
from allura.lib.widgets import form_fields as ffw
from allura.lib.widgets import forms as forms
from allura.lib.widgets import project_list as plw
from allura.lib import plugin
from allura.lib import exceptions as forge_exc
from .auth import AuthController
from .search import SearchController, ProjectBrowseController
from .static import NewForgeController

from allura.model.session import main_orm_session

class W:
    markdown_editor = ffw.MarkdownEdit()
    project_summary = plw.ProjectSummary()
    add_project = forms.NeighborhoodAddProjectForm()
    page_list = ffw.PageList()
    page_size = ffw.PageSize()

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
        if not h.re_path_portion.match(pname):
            raise exc.HTTPNotFound, pname
        project = M.Project.query.get(shortname=self.prefix + pname)
        if project is None:
            project = M.Project.query.get(
                shortname='--init--',
                neighborhood_id=self.neighborhood._id)
            if not project:
                # Go ahead and register it
                project_reg = plugin.ProjectRegistrationProvider.get()
                users = M.User.query.find(dict(_id={'$in':self.neighborhood.acl.admin})).all()
                project = project_reg.register_neighborhood_project(self.neighborhood, users)
            if project:
                c.project = project
                return ProjectController()._lookup(pname, *remainder)
        c.project = project
        if project is None or (project.deleted and not has_project_access('update')()):
            raise exc.HTTPNotFound, pname
        if project.neighborhood.name != self.neighborhood_name:
            redirect(project.url())
        return ProjectController(), remainder

    @expose('allura.templates.neighborhood_project_list')
    @with_trailing_slash
    def index(self, sort='alpha', limit=None, page=0, **kw):
        if self.neighborhood.redirect:
            redirect(self.neighborhood.redirect)
        c.project_summary = W.project_summary
        c.page_list = W.page_list
        c.page_size = W.page_size
        limit, page, start = g.handle_paging(limit, page)
        pq = M.Project.query.find(dict(
                neighborhood_id=self.neighborhood._id,
                deleted=False,
                shortname={'$ne':'--init--'}
                ))
        if sort=='alpha':
            pq.sort('name')
        else:
            pq.sort('last_updated', pymongo.DESCENDING)
        count = pq.count()
        projects = pq.skip(start).limit(int(limit)).all()
        categories = M.ProjectCategory.query.find({'parent_id':None}).sort('name').all()
        c.custom_sidebar_menu = [SitemapEntry('+ Add a Project', self.neighborhood.url()+'add_project'), SitemapEntry('')]
        c.custom_sidebar_menu = c.custom_sidebar_menu + [
            SitemapEntry(cat.label, self.neighborhood.url()+'browse/'+cat.name, className='nav_child') for cat in categories
        ]
        return dict(neighborhood=self.neighborhood,
                    title="Welcome to "+self.neighborhood.name,
                    text=g.markdown.convert(self.neighborhood.homepage),
                    projects=projects,
                    sort=sort,
                    limit=limit, page=page, count=count)

    @expose('allura.templates.neighborhood_add_project')
    def add_project(self, project_unixname=None, project_description=None, project_name=None):
        require(has_neighborhood_access('create', self.neighborhood), 'Create access required')
        c.add_project = W.add_project
        form_data = dict(project_unixname=project_unixname,
                         project_description=project_description,
                         project_name=project_name)
        return dict(neighborhood=self.neighborhood, form_data=form_data)

    @h.vardec
    @expose()
    @validate(W.add_project, error_handler=add_project)
    def register(self, project_unixname=None, project_description=None, project_name=None):
        require(has_neighborhood_access('create', self.neighborhood), 'Create access required')
        try:
            p = self.neighborhood.register_project(project_unixname.lower())
        except forge_exc.ProjectConflict:
            flash(
                'A project already exists with that name, please choose another.', 'error')
            ming.orm.ormsession.ThreadLocalORMSession.close_all()
            redirect('add_project?project_unixname=%s&project_description=%s&project_name=%s' %
                     (project_unixname,project_description,project_name))
        except Exception, ex:
            c.project = None
            ming.orm.ormsession.ThreadLocalORMSession.close_all()
            flash('%s: %s' % (ex.__class__, str(ex)), 'error')
            redirect('add_project?project_unixname=%s&project_description=%s&project_name=%s' %
                     (project_unixname,project_description,project_name))
        if project_name:
            p.name = project_name
        if project_description:
            p.short_description = project_description
        flash('Welcome to the SourceForge Beta System!'
              'To get started, please fill out some information about your '
              'project. Next, you may want to check out the "Tools" screen '
              'and install some tools for your project.')
        redirect(p.script_name + 'admin/overview')

    @expose()
    def icon(self):
        icon = self.neighborhood.icon
        if not icon:
            raise exc.HTTPNotFound
        with icon.open() as fp:
            filename = fp.metadata['filename'].encode('utf-8')
            response.headers['Content-Type'] = ''
            response.content_type = fp.content_type.encode('utf-8')
            return fp.read()
        return icon.filename

    @expose()
    @without_trailing_slash
    def site_style(self):
        """Display the css for the default theme."""
        theme = M.Theme.query.find(dict(neighborhood_id=self.neighborhood._id)).first()
        if theme == None:
            theme = M.Theme.query.find(dict(name='forge_default')).first()

        colors = dict(color1=theme.color1,
                      color2=theme.color2,
                      color3=theme.color3,
                      color4=theme.color4,
                      color5=theme.color5,
                      color6=theme.color6,
                      g=g)
        tpl_fn = pkg_resources.resource_filename(
            'allura', 'templates/style.css')
        css = h.render_genshi_plaintext(tpl_fn,**colors)
        if self.neighborhood.css:
            tt = genshi.template.NewTextTemplate(self.neighborhood.css)
            stream = tt.generate(**colors)
            css = css + stream.render(encoding='utf-8').decode('utf-8')
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
        category_name=unquote(category_name)
        return NeighborhoodProjectBrowseController(neighborhood=self.neighborhood, category_name=category_name, parent_category=self.category), remainder

    @expose('allura.templates.neighborhood_project_list')
    @without_trailing_slash
    def index(self, sort='alpha', limit=None, page=0, **kw):
        c.project_summary = W.project_summary
        c.page_list = W.page_list
        c.page_size = W.page_size
        limit, page, start = g.handle_paging(limit, page)
        projects, count = self._find_projects(sort=sort, limit=limit, start=start)
        title=self._build_title()
        c.custom_sidebar_menu = self._build_nav()
        return dict(projects=projects,
                    title=title,
                    text=None,
                    neighborhood=self.neighborhood,
                    sort=sort,
                    limit=limit, page=page, count=count)

class HostNeighborhoodController(BaseController, NeighborhoodController):
    '''Neighborhood controller with support for use as a root controller, for
    instance, when using adobe.sourceforge.net (if this is allowed).
    '''

    auth = AuthController()
    error = ErrorController()
    nf = NewForgeController()
    search = SearchController()

class ProjectController(object):

    def __init__(self):
        setattr(self, 'feed.rss', self.feed)
        setattr(self, 'feed.atom', self.feed)
        setattr(self, '_nav.json', self._nav)
        self.screenshot = ScreenshotsController()

    @expose('json:')
    def _nav(self):
        return dict(menu=[
                dict(name=s.label, url=s.url, icon=s.ui_icon)
                for s in c.project.sitemap() ])

    @expose()
    def _lookup(self, name, *remainder):
        name=unquote(name)
        if not h.re_path_portion.match(name):
            raise exc.HTTPNotFound, name
        subproject = M.Project.query.get(shortname=c.project.shortname + '/' + name, deleted=False)
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
    def index(self, **kw):
        if c.project.app_instance('home'):
            redirect('home/')
        elif c.project.app_instance('profile'):
            redirect('profile/')
        else:
            redirect(c.project.app_configs[0].options.mount_point + '/')

    @expose('allura.templates.project_sitemap')
    @without_trailing_slash
    def sitemap(self): # pragma no cover
        raise NotImplementedError, 'sitemap'
        require(has_project_access('read'))
        return dict()

    @without_trailing_slash
    @expose()
    @validate(dict(
            since=h.DateTimeConverter(if_empty=None),
            until=h.DateTimeConverter(if_empty=None),
            page=validators.Int(if_empty=None),
            limit=validators.Int(if_empty=None)))
    def feed(self, since=None, until=None, page=None, limit=None):
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
            since, until, page, limit)
        response.headers['Content-Type'] = ''
        response.content_type = 'application/xml'
        return feed.writeString('utf-8')

    @expose()
    def icon(self):
        icon = c.project.icon
        if not icon:
            raise exc.HTTPNotFound
        with icon.open() as fp:
            filename = fp.metadata['filename'].encode('utf-8')
            response.headers['Content-Type'] = ''
            response.content_type = fp.content_type.encode('utf-8')
            return fp.read()
        return icon.filename

    @expose()
    def user_icon(self):
        try:
            return self.icon()
        except exc.HTTPNotFound:
            redirect(g.forge_static('images/user.png'))

    @expose('json:')
    def user_search(self,term=''):
        name_regex = re.compile('(?i)%s' % re.escape(term))
        users = M.User.query.find({
                    '_id':{'$in':[role.user_id for role in c.project.roles]},
                    'display_name':name_regex},
                    ['display_name','username'])
        users = [dict(label='%s (%s)' % (u.display_name, u.username),
                      value=u.username,
                      id=u.username) for u in users.sort('username').all()]
        return dict(users=users)

class ScreenshotsController(object):

    @expose()
    def _lookup(self, filename, *args):
        filename=unquote(filename)
        return ScreenshotController(filename), args

class ScreenshotController(object):

    def __init__(self, filename):
        self.filename = filename

    @expose()
    def index(self, embed=True, **kw):
        screenshot = M.ProjectFile.query.find({'metadata.project_id':c.project._id, 'metadata.category':'screenshot', 'filename':self.filename}).first()
        with screenshot.open() as fp:
            filename = fp.metadata['filename'].encode('utf-8')
            response.headers['Content-Type'] = ''
            response.content_type = fp.content_type.encode('utf-8')
            if not embed:
                response.headers.add('Content-Disposition',
                                     'attachment;filename=%s' % filename)
            return fp.read()
        return self.filename

    @expose()
    def thumb(self, embed=True):
        thumb = M.ProjectFile.query.find({'metadata.project_id':c.project._id, 'metadata.category':'screenshot_thumb', 'metadata.filename':self.filename}).first()
        with thumb.open() as fp:
            filename = fp.metadata['filename'].encode('utf-8')
            response.headers['Content-Type'] = ''
            response.content_type = fp.content_type.encode('utf-8')
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

    def set_nav(self):
        project = M.Project.query.find({'shortname':'--init--','neighborhood_id':self.neighborhood._id}).first()
        if project:
            c.project = project
            g.set_app('admin')
        else:
            admin_url = self.neighborhood.url()+'_admin/'
            c.custom_sidebar_menu = [
                     SitemapEntry('Overview', admin_url+'overview', className='nav_child'),
                     SitemapEntry('Permissions', admin_url+'permissions', className='nav_child'),
                     SitemapEntry('Awards', admin_url+'accolades', className='nav_child')]

    @with_trailing_slash
    @expose()
    def index(self, **kw):
        redirect('overview')

    @without_trailing_slash
    @expose('allura.templates.neighborhood_admin_overview')
    def overview(self):
        self.set_nav()
        c.markdown_editor = W.markdown_editor
        return dict(neighborhood=self.neighborhood)

    @without_trailing_slash
    @expose('allura.templates.neighborhood_admin_permissions')
    def permissions(self):
        self.set_nav()
        return dict(neighborhood=self.neighborhood)

    @without_trailing_slash
    @expose('allura.templates.neighborhood_admin_accolades')
    def accolades(self):
        self.set_nav()
        psort = [(n, M.Project.query.find(dict(is_root=True, neighborhood_id=n._id, deleted=False)).sort('shortname').all())
                 for n in M.Neighborhood.query.find().sort('name')]
        awards = M.Award.query.find(dict(created_by_neighborhood_id=self.neighborhood._id))
        awards_count = len(awards)
        assigns = M.Award.query.find(dict(created_by_neighborhood_id=self.neighborhood._id))
        assigns_count = len(assigns)
        grants = M.AwardGrant.query.find(dict(granted_by_neighborhood_id=self.neighborhood._id))
        grants_count = len(grants)
        return dict(
            projects=psort,
            awards=awards,
            awards_count=awards_count,
            assigns=assigns,
            assigns_count=assigns_count,
            grants=grants,
            grants_count=grants_count,
            neighborhood=self.neighborhood)

    @expose()
    def update(self, name=None, css=None, homepage=None, icon=None,
               color1=None, color2=None, color3=None, color4=None, color5=None, color6=None,
               **kw):
        self.neighborhood.name = name
        self.neighborhood.redirect = kw.pop('redirect', '')
        self.neighborhood.homepage = homepage
        self.neighborhood.css = css
        self.neighborhood.allow_browse = 'allow_browse' in kw
        if color1 or color2 or color3 or color4 or color5 or color6:
            if not self.neighborhood.theme:
                theme = M.Theme(neighborhood_id=self.neighborhood._id)
            else:
                theme = self.neighborhood.theme
            theme.color1 = color1
            theme.color2 = color2
            theme.color3 = color3
            theme.color4 = color4
            theme.color5 = color5
            theme.color6 = color6
        if icon is not None and icon != '':
            if self.neighborhood.icon:
                M.NeighborhoodFile.query.remove({'metadata.neighborhood_id':self.neighborhood._id})
            h.save_image(icon, M.NeighborhoodFile, square=True, thumbnail_size=(48, 48), meta=dict(neighborhood_id=self.neighborhood._id))
        redirect('overview')

    @h.vardec
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
            u = M.User.by_username(new['username'])
            self.neighborhood.acl[permission].append(u._id)
        redirect('permissions')

class NeighborhoodModerateController(object):

    def __init__(self, neighborhood):
        self.neighborhood = neighborhood

    def _check_security(self):
        require(has_neighborhood_access('moderate', self.neighborhood),
                'Moderator access required')

    @expose('allura.templates.neighborhood_moderate')
    def index(self, **kw):
        return dict(neighborhood=self.neighborhood)

    @expose()
    def invite(self, pid, invite=None, uninvite=None):
        p = M.Project.query.get(shortname=pid, deleted=False)
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
        p = M.Project.query.get(shortname=pid, neighborhood_id=self.neighborhood._id, deleted=False)
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

    @expose('allura.templates.awards')
    def index(self, **kw):
        awards = M.Award.query.find(dict(created_by_neighborhood_id=self.neighborhood._id))
        count=0
        count = len(awards)
        return dict(awards=awards or [], count=count)

    @expose('allura.templates.not_found')
    def not_found(self, **kw):
        return dict()

    @expose('allura.templates.grants')
    def grants(self, **kw):
        grants = M.AwardGrant.query.find(dict(granted_by_neighborhood_id=self.neighborhood._id))
        count=0
        count = len(grants)
        return dict(grants=grants or [], count=count)

    @expose()
    def _lookup(self, short, *remainder):
        short=unquote(short)
        return AwardController(short), remainder

    @expose()
    def create(self, icon=None, short=None, full=None):
        if request.method != 'POST':
            raise Exception('award_save must be a POST request')
        app_config_id = ObjectId()
        tool_version = { 'neighborhood':'0' }
        if short is not None:
            award = M.Award(app_config_id=app_config_id, tool_version=tool_version)
            award.short = short
            award.full = full
            award.created_by_neighborhood_id = self.neighborhood._id
            h.save_image(icon, M.AwardFile, square=True, thumbnail_size=(48, 48), meta=dict(award_id=award._id))
        redirect(request.referer)

    @expose()
    def grant(self, grant=None, recipient=None):
        if request.method != 'POST':
            raise Exception('award_grant must be a POST request')
        grant_q = M.Award.query.find(dict(short=grant)).first()
        recipient_q = M.Project.query.find(dict(name=recipient, deleted=False)).first()
        app_config_id = ObjectId()
        tool_version = { 'neighborhood':'0' }
        award = M.AwardGrant(app_config_id=app_config_id, tool_version=tool_version)
        award.award_id = grant_q._id
        award.granted_to_project_id = recipient_q._id
        award.granted_by_neighborhood_id = self.neighborhood._id
        redirect(request.referer)

class AwardController(object):

    def __init__(self, short=None):
        if short is not None:
            self.short = short
            self.award = M.Award.query.get(short=self.short)

    @with_trailing_slash
    @expose('allura.templates.award')
    def index(self, **kw):
        if self.award is not None:
            return dict(award=self.award)
        else:
            redirect('not_found')

    @expose('allura.templates.not_found')
    def not_found(self, **kw):
        return dict()

    @expose()
    def _lookup(self, recipient, *remainder):
        recipient=unquote(recipient)
        return GrantController(self.award, recipient), remainder

    @expose()
    def icon(self):
        icon = self.award.icon
        if not icon:
            raise exc.HTTPNotFound
        with icon.open() as fp:
            filename = fp.metadata['filename'].encode('utf-8')
            response.headers['Content-Type'] = ''
            response.content_type = fp.content_type.encode('utf-8')
            return fp.read()
        return icon.filename

    @expose()
    def grant(self, recipient=None):
        if request.method != 'POST':
            raise Exception('award_grant must be a POST request')
        recipient_q = M.Project.query.find(dict(name=recipient, deleted=False)).first()
        app_config_id = ObjectId()
        tool_version = { 'neighborhood':'0' }
        grant = M.AwardGrant(app_config_id=app_config_id, tool_version=tool_version)
        grant.award_id = self.award._id
        grant.granted_to_project_id = recipient_q._id
        grant.granted_by_neighborhood_id = self.neighborhood._id
        redirect(request.referer)

    @expose()
    def delete(self):
        if self.award:
            grants = M.AwardGrant.query.find(dict(award_id=self.award._id))
            for grant in grants:
                grant.delete()
            M.AwardFile.query.remove({'metadata.award_id':self.award._id})
            self.award.delete()
        redirect('../..')

class GrantController(object):

    def __init__(self, award=None, recipient=None):
        if recipient is not None and award is not None:
            self.recipient = recipient.replace('users_','users/')
            self.award = M.Award.query.get(_id=award._id)
            self.project = M.Project.query.get(shortname=self.recipient)
            self.grant = M.AwardGrant.query.get(award_id=self.award._id,
                granted_to_project_id=self.project._id)

    @with_trailing_slash
    @expose('allura.templates.grant')
    def index(self, **kw):
        if self.grant is not None:
            return dict(grant=self.grant)
        else:
            redirect('not_found')

    @expose('allura.templates.not_found')
    def not_found(self, **kw):
        return dict()

    @expose()
    def icon(self):
        icon = self.award.icon
        if not icon:
            raise exc.HTTPNotFound
        with icon.open() as fp:
            filename = fp.metadata['filename'].encode('utf-8')
            response.headers['Content-Type'] = ''
            response.content_type = fp.content_type.encode('utf-8')
            return fp.read()
        return icon.filename

    @expose()
    def revoke(self):
        self.grant.delete()
        redirect(request.referer)

