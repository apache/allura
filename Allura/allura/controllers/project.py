import re
import logging

from bson import ObjectId
from urllib import unquote
from itertools import chain, islice

from tg import expose, flash, redirect, validate, request, response
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import c, g
from webob import exc
import pymongo
from formencode import validators

from ming.utils import LazyProperty

from allura import model as M
from allura.app import SitemapEntry
from allura.lib.base import WsgiDispatchController
from allura.lib import helpers as h
from allura.lib import utils
from allura.lib.decorators import require_post
from allura.controllers.error import ErrorController
from allura.lib.security import require_access, has_access
from allura.lib.security import RoleCache
from allura.lib.widgets import forms as ff
from allura.lib.widgets import form_fields as ffw
from allura.lib.widgets import project_list as plw
from allura.lib import plugin
from .auth import AuthController
from .search import SearchController, ProjectBrowseController
from .static import NewForgeController

log = logging.getLogger(__name__)

class W:
    resize_editor = ffw.AutoResizeTextarea()
    project_summary = plw.ProjectSummary()
    add_project = plugin.ProjectRegistrationProvider.get().add_project_widget(antispam=True)
    page_list = ffw.PageList()
    page_size = ffw.PageSize()
    project_select = ffw.NeighborhoodProjectSelect
    neighborhood_overview_form = ff.NeighborhoodOverviewForm()

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
        require_access(self.neighborhood, 'read')

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

    @expose('jinja:allura:templates/neighborhood_project_list.html')
    @with_trailing_slash
    def index(self, sort='alpha', limit=25, page=0, **kw):
        c.project = self.neighborhood.neighborhood_project
        if self.neighborhood.redirect:
            redirect(self.neighborhood.redirect)
        c.project_summary = W.project_summary
        c.page_list = W.page_list
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
        nb_max_projects = self.neighborhood.get_max_projects()
        projects = pq.skip(start).limit(int(limit)).all()
        categories = M.ProjectCategory.query.find({'parent_id':None}).sort('name').all()
        c.custom_sidebar_menu = []
        if h.has_access(self.neighborhood, 'register')() and (nb_max_projects is None or count < nb_max_projects):
            c.custom_sidebar_menu += [
                SitemapEntry('Add a Project', self.neighborhood.url()+'add_project', ui_icon=g.icons['plus']),
                SitemapEntry('')
            ]
        c.custom_sidebar_menu = c.custom_sidebar_menu + [
            SitemapEntry(cat.label, self.neighborhood.url()+'browse/'+cat.name, className='nav_child') for cat in categories
        ]
        return dict(neighborhood=self.neighborhood,
                    title="Welcome to "+self.neighborhood.name,
                    text=g.markdown.convert(self.neighborhood.homepage),
                    projects=projects,
                    sort=sort,
                    limit=limit, page=page, count=count)

    @expose('jinja:allura:templates/neighborhood_add_project.html')
    @without_trailing_slash
    def add_project(self, **form_data):
        c.project = self.neighborhood.neighborhood_project
        require_access(self.neighborhood, 'register')
        c.add_project = W.add_project
        form_data['tools'] = ['Wiki','Git','Tickets','Downloads','Discussion']
        form_data['neighborhood'] = self.neighborhood.name
        return dict(neighborhood=self.neighborhood, form_data=form_data)

    @expose('json:')
    def suggest_name(self, project_name=None):
        new_name = re.sub("[^A-Za-z0-9]", "", project_name).lower()
        name_taken_message = plugin.ProjectRegistrationProvider.get().name_taken(new_name, self.neighborhood)
        if len(new_name) < 3 or len(new_name) > 15:
            name_taken_message = "Name must be 3-15 characters long."
        return dict(suggested_name=new_name, message=name_taken_message)

    @expose('json:')
    def check_name(self, project_name=None):
        name_taken_message = plugin.ProjectRegistrationProvider.get().name_taken(project_name, self.neighborhood)
        if not name_taken_message and not h.re_path_portion.match(project_name):
            name_taken_message = 'Please use only letters, numbers, and dashes 3-15 characters long.'
        return dict(message=name_taken_message)

    @h.vardec
    @expose()
    @validate(W.add_project, error_handler=add_project)
    @utils.AntiSpam.validate('Spambot protection engaged')
    @require_post()
    def register(self, project_unixname=None, project_description=None, project_name=None, neighborhood=None,
                 private_project=None, tools=None, **kw):
        require_access(self.neighborhood, 'register')
        if self.neighborhood.allow_private == False:
            private_project = False
        if private_project:
            require_access(self.neighborhood, 'admin')
        neighborhood = M.Neighborhood.query.get(name=neighborhood)

        pq = M.Project.query.find(dict(
                neighborhood_id=neighborhood._id,
                deleted=False,
                shortname={'$ne':'--init--'}
                ))
        count = pq.count()
        nb_max_projects = neighborhood.get_max_projects()
        if nb_max_projects is not None and count >= nb_max_projects:
            flash("You have exceeded the maximum number of projects you are allowed to create"\
                  "(%s of %s projects)" % (count, nb_max_projects), 'error')
            redirect('.')

        project_description = h.really_unicode(project_description or '').encode('utf-8')
        project_name = h.really_unicode(project_name or '').encode('utf-8')
        project_unixname = h.really_unicode(project_unixname or '').encode('utf-8').lower()
        c.project = neighborhood.register_project(project_unixname,
                project_name=project_name, private_project=private_project)
        if project_description:
            c.project.short_description = project_description
        offset = c.project.next_mount_point(include_search=True)
        if tools and not neighborhood.project_template:
            for i, tool in enumerate(tools):
                c.project.install_app(tool, ordinal=i+offset)
        flash('Welcome to the SourceForge Beta System! '
              'To get started, fill out some information about your project.')
        redirect(c.project.script_name + 'admin/overview')

    @expose()
    def icon(self):
        icon = self.neighborhood.icon
        if not icon:
            raise exc.HTTPNotFound
        return icon.serve()

class NeighborhoodProjectBrowseController(ProjectBrowseController):
    def __init__(self, neighborhood=None, category_name=None, parent_category=None):
        self.neighborhood = neighborhood
        super(NeighborhoodProjectBrowseController, self).__init__(category_name=category_name, parent_category=parent_category)
        self.nav_stub = '%sbrowse/' % self.neighborhood.url()
        self.additional_filters = {'neighborhood_id':self.neighborhood._id}

    @expose()
    def _lookup(self, category_name, *remainder):
        c.project = self.neighborhood.neighborhood_project
        category_name=unquote(category_name)
        return NeighborhoodProjectBrowseController(neighborhood=self.neighborhood, category_name=category_name, parent_category=self.category), remainder

    @expose('jinja:allura:templates/neighborhood_project_list.html')
    @without_trailing_slash
    def index(self, sort='alpha', limit=25, page=0, **kw):
        c.project_summary = W.project_summary
        c.page_list = W.page_list
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

class HostNeighborhoodController(WsgiDispatchController, NeighborhoodController):
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
        subproject = M.Project.query.get(shortname=c.project.shortname + '/' + name,
                                         neighborhood_id=c.project.neighborhood_id)
        if subproject:
            c.project = subproject
            c.app = None
            return ProjectController(), remainder
        app = c.project.app_instance(name)
        if app is None:
            raise exc.HTTPNotFound, name
        c.app = app
        if not app.root:
            raise exc.HTTPNotFound, name

        return app.root, remainder

    def _check_security(self):
        require_access(c.project, 'read')

    @expose()
    @with_trailing_slash
    def index(self, **kw):
        mount = c.project.first_mount('read')
        if mount is not None:
            if 'ac' in mount:
                redirect(mount['ac'].options.mount_point + '/')
            elif 'sub' in mount:
                redirect(mount['sub'].url())
        elif c.project.app_instance('profile'):
            redirect('profile/')
        else:
            redirect(c.project.app_configs[0].options.mount_point + '/')

    @expose('jinja:allura:templates/project_sitemap.html')
    @without_trailing_slash
    def sitemap(self): # pragma no cover
        raise NotImplementedError, 'sitemap'

    @without_trailing_slash
    @expose()
    @validate(dict(
            since=h.DateTimeConverter(if_empty=None, if_invalid=None),
            until=h.DateTimeConverter(if_empty=None, if_invalid=None),
            page=validators.Int(if_empty=None),
            limit=validators.Int(if_empty=None)))
    def feed(self, since=None, until=None, page=None, limit=None):
        if request.environ['PATH_INFO'].endswith('.atom'):
            feed_type = 'atom'
        else:
            feed_type = 'rss'
        title = 'Recent changes to Project %s' % c.project.name
        feed = M.Feed.feed(
            dict(project_id=c.project._id),
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
        return icon.serve()

    @expose()
    def user_icon(self):
        try:
            return self.icon()
        except exc.HTTPNotFound:
            redirect(g.forge_static('images/user.png'))

    @expose('json:')
    def user_search(self,term=''):
        if len(term) < 3:
            raise exc.HTTPBadRequest('"term" param must be at least length 3')
        users = M.User.by_display_name(term)
        named_roles = RoleCache(
            g.credentials,
            g.credentials.project_roles(project_id=c.project.root_project._id).named)
        result = [ [], [] ]
        for u in users:
            if u._id in named_roles.userids_that_reach:
                result[0].append(u)
            else:
                pass
                # comment this back in if you want non-project-member users
                # in the search results
                #result[1].append(u)
        result = list(islice(chain(*result), 10))
        return dict(
            users=[
                dict(
                    label='%s (%s)' % (u.get_pref('display_name'), u.username),
                    value=u.username,
                    id=u.username)
                for u in result])

class ScreenshotsController(object):

    @expose()
    def _lookup(self, filename, *args):
        if args:
            filename=unquote(filename)
        else:
            filename = unquote(request.path.rsplit('/', 1)[-1])
        return ScreenshotController(filename), args

class ScreenshotController(object):

    def __init__(self, filename):
        self.filename = filename

    @expose()
    def index(self, embed=True, **kw):
        return self._screenshot.serve(embed)

    @expose()
    def thumb(self, embed=True):
        return self._thumb.serve(embed)

    @LazyProperty
    def _screenshot(self):
        f = M.ProjectFile.query.get(
            project_id=c.project._id,
            category='screenshot',
            filename=self.filename)
        if not f: raise exc.HTTPNotFound
        return f

    @LazyProperty
    def _thumb(self):
        f = M.ProjectFile.query.get(
            project_id=c.project._id,
            category='screenshot_thumb',
            filename=self.filename)
        if not f: raise exc.HTTPNotFound
        return f

def set_nav(neighborhood):
    project = neighborhood.neighborhood_project
    if project:
        c.project = project
        g.set_app('admin')
    else:
        admin_url = neighborhood.url() + '_admin/'
        c.custom_sidebar_menu = [
            SitemapEntry('Overview', admin_url + 'overview', className='nav_child'),
            SitemapEntry('Awards', admin_url + 'accolades', className='nav_child')]

class NeighborhoodAdminController(object):
    def __init__(self, neighborhood):
        self.neighborhood = neighborhood
        self.awards = NeighborhoodAwardsController(self.neighborhood)

    @with_trailing_slash
    @expose()
    def index(self, **kw):
        require_access(self.neighborhood, 'admin')
        utils.permanent_redirect('overview')

    @without_trailing_slash
    @expose('jinja:allura:templates/neighborhood_admin_overview.html')
    def overview(self, **kw):
        require_access(self.neighborhood, 'admin')
        set_nav(self.neighborhood)
        c.overview_form = W.neighborhood_overview_form
        return dict(neighborhood=self.neighborhood)

    @without_trailing_slash
    @expose('jinja:allura:templates/neighborhood_admin_permissions.html')
    def permissions(self):
        require_access(self.neighborhood, 'admin')
        set_nav(self.neighborhood)
        return dict(neighborhood=self.neighborhood)

    @expose('json:')
    def project_search(self, term=''):
        require_access(self.neighborhood, 'admin')
        if len(term) < 3:
            raise exc.HTTPBadRequest('"term" param must be at least length 3')
        project_regex = re.compile('(?i)%s' % re.escape(term))
        projects = M.Project.query.find(dict(
            neighborhood_id=self.neighborhood._id, deleted=False,
            shortname=project_regex)).sort('shortname')
        return dict(
            projects=[
                dict(
                    label=p.shortname,
                    value=p.shortname,
                    id=p.shortname)
                for p in projects])

    @without_trailing_slash
    @expose('jinja:allura:templates/neighborhood_admin_accolades.html')
    def accolades(self):
        require_access(self.neighborhood, 'admin')
        set_nav(self.neighborhood)
        awards = M.Award.query.find(dict(created_by_neighborhood_id=self.neighborhood._id)).all()
        awards_count = len(awards)
        grants = M.AwardGrant.query.find(dict(granted_by_neighborhood_id=self.neighborhood._id))
        grants_count = len(grants)
        c.project_select = W.project_select(self.neighborhood.url() + '_admin/project_search')
        return dict(
            awards=awards,
            awards_count=awards_count,
            grants=grants,
            grants_count=grants_count,
            neighborhood=self.neighborhood)

    @expose()
    @require_post()
    @validate(W.neighborhood_overview_form, error_handler=overview)
    def update(self, name=None, css=None, homepage=None, project_template=None, icon=None, **kw):
        require_access(self.neighborhood, 'admin')
        self.neighborhood.name = name
        self.neighborhood.redirect = kw.pop('redirect', '')
        self.neighborhood.homepage = homepage
        self.neighborhood.css = css
        self.neighborhood.project_template = project_template
        self.neighborhood.allow_browse = kw['allow_browse'] if 'allow_browse' in kw else False
        if self.neighborhood.should_show_icon() and icon is not None and icon != '':
            if self.neighborhood.icon:
                self.neighborhood.icon.delete()
            M.NeighborhoodFile.save_image(
                icon.filename, icon.file, content_type=icon.type,
                square=True, thumbnail_size=(48,48),
                thumbnail_meta=dict(neighborhood_id=self.neighborhood._id))
        redirect('overview')


class NeighborhoodModerateController(object):

    def __init__(self, neighborhood):
        self.neighborhood = neighborhood

    def _check_security(self):
        require_access(self.neighborhood, 'admin')

    @expose('jinja:allura:templates/neighborhood_moderate.html')
    def index(self, **kw):
        other_nbhds = list(M.Neighborhood.query.find(dict(_id={'$ne':self.neighborhood._id})).sort('name'))
        return dict(neighborhood=self.neighborhood,
                    neighborhoods=other_nbhds)

    @expose()
    @require_post()
    def invite(self, pid, neighborhood_id, invite=None, uninvite=None):
        p = M.Project.query.get(shortname=pid, deleted=False,
                                neighborhood_id=ObjectId(neighborhood_id))
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
    @require_post()
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

    @expose('jinja:allura:templates/awards.html')
    def index(self, **kw):
        require_access(self.neighborhood, 'admin')
        awards = M.Award.query.find(dict(created_by_neighborhood_id=self.neighborhood._id))
        count = len(awards)
        return dict(awards=awards or [], count=count)

    @expose('jinja:allura:templates/award_not_found.html')
    def not_found(self, **kw):
        return dict()

    @expose('jinja:allura:templates/grants.html')
    def grants(self, **kw):
        require_access(self.neighborhood, 'admin')
        grants = M.AwardGrant.query.find(dict(granted_by_neighborhood_id=self.neighborhood._id))
        count = len(grants)
        return dict(grants=grants or [], count=count)

    @expose()
    def _lookup(self, award_id, *remainder):
        return AwardController(self.neighborhood, award_id), remainder

    @expose()
    @require_post()
    def create(self, icon=None, short=None, full=None):
        require_access(self.neighborhood, 'admin')
        app_config_id = ObjectId()
        tool_version = {'neighborhood': '0'}
        if short:
            award = M.Award(app_config_id=app_config_id, tool_version=tool_version)
            award.short = short
            award.full = full
            award.created_by_neighborhood_id = self.neighborhood._id
            if hasattr(icon, 'filename'):
                M.AwardFile.save_image(
                    icon.filename, icon.file, content_type=icon.type,
                    square=True, thumbnail_size=(48,48),
                    thumbnail_meta=dict(award_id=award._id))
        redirect(request.referer)

    @expose()
    @require_post()
    def grant(self, grant=None, recipient=None):
        require_access(self.neighborhood, 'admin')
        grant_q = M.Award.query.find(dict(short=grant,
            created_by_neighborhood_id=self.neighborhood._id)).first()
        recipient_q = M.Project.query.find(dict(
            neighborhood_id=self.neighborhood._id, shortname=recipient,
            deleted=False)).first()
        if grant_q and recipient_q:
            app_config_id = ObjectId()
            tool_version = {'neighborhood': '0'}
            award = M.AwardGrant(app_config_id=app_config_id,
                                 tool_version=tool_version)
            award.award_id = grant_q._id
            award.granted_to_project_id = recipient_q._id
            award.granted_by_neighborhood_id = self.neighborhood._id
            with h.push_context(recipient_q._id):
                g.post_event('project_updated')
        redirect(request.referer)

class AwardController(object):

    def __init__(self, neighborhood=None, award_id=None):
        self.neighborhood = neighborhood
        if award_id:
            self.award = M.Award.query.find(dict(_id=ObjectId(award_id),
                created_by_neighborhood_id=self.neighborhood._id)).first()

    @with_trailing_slash
    @expose('jinja:allura:templates/award.html')
    def index(self, **kw):
        require_access(self.neighborhood, 'admin')
        set_nav(self.neighborhood)
        if self.award is not None:
            return dict(award=self.award, neighborhood=self.neighborhood)
        else:
            redirect('not_found')

    @expose('jinja:allura:templates/award_not_found.html')
    def not_found(self, **kw):
        return dict()

    @expose()
    def _lookup(self, recipient, *remainder):
        recipient=unquote(recipient)
        return GrantController(self.neighborhood, self.award, recipient), remainder

    @expose()
    def icon(self):
        icon = self.award.icon
        if not icon:
            raise exc.HTTPNotFound
        return icon.serve()

    @expose()
    @require_post()
    def update(self, icon=None, short=None, full=None):
        require_access(self.neighborhood, 'admin')
        self.award.short = short
        self.award.full = full
        if hasattr(icon, 'filename'):
            if self.award.icon:
                self.award.icon.delete()
            M.AwardFile.save_image(
                icon.filename, icon.file, content_type=icon.type,
                square=True, thumbnail_size=(48,48),
                thumbnail_meta=dict(award_id=self.award._id))
        for grant in M.AwardGrant.query.find(dict(award_id=self.award._id)):
            with h.push_context(grant.granted_to_project_id):
                g.post_event('project_updated')
        flash('Award updated.')
        redirect(self.award.longurl())

    @expose()
    @require_post()
    def delete(self):
        require_access(self.neighborhood, 'admin')
        if self.award:
            grants = M.AwardGrant.query.find(dict(award_id=self.award._id))
            for grant in grants:
                grant.delete()
                with h.push_context(grant.granted_to_project_id):
                    g.post_event('project_updated')
            M.AwardFile.query.remove(dict(award_id=self.award._id))
            self.award.delete()
        redirect(request.referer)

class GrantController(object):

    def __init__(self, neighborhood=None, award=None, recipient=None):
        self.neighborhood = neighborhood
        if recipient is not None and award is not None:
            self.recipient = recipient.replace('_', '/')
            self.award = M.Award.query.get(_id=award._id)
            self.project = M.Project.query.find(dict(shortname=self.recipient,
                neighborhood_id=self.neighborhood._id)).first()
            self.grant = M.AwardGrant.query.get(award_id=self.award._id,
                granted_to_project_id=self.project._id)

    @with_trailing_slash
    @expose('jinja:allura:templates/grant.html')
    def index(self, **kw):
        require_access(self.neighborhood, 'admin')
        if self.grant is not None:
            return dict(grant=self.grant)
        else:
            redirect('not_found')

    @expose('jinja:allura:templates/award_not_found.html')
    def not_found(self, **kw):
        return dict()

    @expose()
    def icon(self):
        icon = self.award.icon
        if not icon:
            raise exc.HTTPNotFound
        return icon.serve()

    @expose()
    @require_post()
    def revoke(self):
        require_access(self.neighborhood, 'admin')
        self.grant.delete()
        with h.push_context(self.project._id):
            g.post_event('project_updated')
        redirect(request.referer)
