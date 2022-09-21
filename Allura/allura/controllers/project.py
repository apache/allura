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

import re
import logging
from datetime import datetime, timedelta

import six
from six.moves.urllib.parse import unquote

from bson import ObjectId
from tg import expose, flash, redirect, validate, request, config, session
from tg.decorators import with_trailing_slash, without_trailing_slash
from tg import tmpl_context as c, app_globals as g
from paste.deploy.converters import asbool
from webob import exc
import jinja2
import markupsafe
import pymongo

from ming.utils import LazyProperty

from allura import model as M
from allura.app import SitemapEntry
from allura.lib import helpers as h
from allura.lib.helpers import iter_entry_points
from allura.lib import utils
from allura.lib.decorators import require_post
from allura.controllers.feed import FeedArgs, FeedController
from allura.controllers.rest import nbhd_lookup_first_path
from allura.lib.security import require_access
from allura.lib.security import RoleCache
from allura.lib.widgets import forms as ff
from allura.lib.widgets import form_fields as ffw
from allura.lib.widgets import project_list as plw
from allura.lib import plugin, exceptions
from .search import ProjectBrowseController
from allura.ext.user_profile.user_main import UserProfileApp

log = logging.getLogger(__name__)


class W:
    resize_editor = ffw.AutoResizeTextarea()
    project_summary = plw.ProjectSummary()
    add_project = plugin.ProjectRegistrationProvider.get().add_project_widget(antispam=True)
    page_list = ffw.PageList()
    page_size = ffw.PageSize()
    neighborhood_overview_form = ff.NeighborhoodOverviewForm()
    award_grant_form = ff.AwardGrantForm


class NeighborhoodController:

    '''Manages a neighborhood of projects.
    '''

    def __init__(self, neighborhood):
        self.neighborhood = neighborhood
        self.neighborhood_name = self.neighborhood.name
        self.browse = NeighborhoodProjectBrowseController(neighborhood=self.neighborhood)
        # 'admin' without underscore will pass through to _lookup which will find the regular "admin" tool mounted
        # on the --init-- Project record for this neighborhood.
        self._admin = NeighborhoodAdminController(self.neighborhood)
        self._moderate = NeighborhoodModerateController(self.neighborhood)
        self.import_project = ProjectImporterController(self.neighborhood)

    def _check_security(self):
        require_access(self.neighborhood, 'read')

    def _before(self, *args, **kwargs):
        # TurboGears runs this before each request
        c.project = self.neighborhood.neighborhood_project

    @expose()
    def _lookup(self, pname, *remainder):
        c.project, remainder = nbhd_lookup_first_path(self.neighborhood, pname, c.user, remainder)
        return ProjectController(), remainder

    @expose('jinja:allura:templates/neighborhood_project_list.html')
    @with_trailing_slash
    def index(self, sort='alpha', limit=25, page=0, **kw):
        text = None
        if self.neighborhood.use_wiki_page_as_root:
            default_wiki_page = get_default_wiki_page()
            if default_wiki_page:
                text = default_wiki_page.html_text
        elif self.neighborhood.redirect:
            redirect(self.neighborhood.redirect)
        elif not self.neighborhood.has_home_tool:
            mount = c.project.ordered_mounts()[0]
            if mount is not None:
                if 'ac' in mount:
                    redirect(mount['ac'].options.mount_point + '/')
                elif 'sub' in mount:
                    redirect(mount['sub'].url())
            else:
                redirect(c.project.app_configs[0].options.mount_point + '/')
        else:
            text=g.markdown.cached_convert(
                self.neighborhood, 'homepage'),

        c.project_summary = W.project_summary
        c.page_list = W.page_list
        limit, page, start = g.handle_paging(limit, page)
        pq = M.Project.query.find(dict(
            neighborhood_id=self.neighborhood._id,
            deleted=False,
            is_nbhd_project=False,
        ))
        if sort == 'alpha':
            pq.sort('name')
        else:
            pq.sort('last_updated', pymongo.DESCENDING)
        count = pq.count()
        nb_max_projects = self.neighborhood.get_max_projects()
        projects = pq.skip(start).limit(int(limit)).all()
        categories = M.ProjectCategory.query.find(
            {'parent_id': None}).sort('name').all()
        c.custom_sidebar_menu = []
        if h.has_access(self.neighborhood, 'register')() and (nb_max_projects is None or count < nb_max_projects):
            c.custom_sidebar_menu += [
                SitemapEntry('Add a Project', self.neighborhood.url()
                             + 'add_project', ui_icon=g.icons['add']),
                SitemapEntry('')
            ]
        c.custom_sidebar_menu = c.custom_sidebar_menu + [
            SitemapEntry(cat.label, self.neighborhood.url() + 'browse/' + cat.name) for cat in categories
        ]
        return dict(neighborhood=self.neighborhood,
                    title="Welcome to " + self.neighborhood.name,
                    text=text,
                    projects=projects,
                    sort=sort,
                    limit=limit, page=page, count=count)

    @expose('jinja:allura:templates/neighborhood_add_project.html')
    @without_trailing_slash
    def add_project(self, **form_data):
        with h.login_overlay():
            require_access(self.neighborhood, 'register')
        verify = c.form_errors == {'_the_form': 'phone-verification'}
        c.show_phone_verification_overlay = verify
        c.add_project = W.add_project
        form_data.setdefault('tools', W.add_project.default_tools)
        form_data['neighborhood'] = self.neighborhood.name
        return dict(neighborhood=self.neighborhood, form_data=form_data)

    @expose('jinja:allura:templates/phone_verification_fragment.html')
    def phone_verification_fragment(self, *args, **kw):
        require_access(self.neighborhood, 'register')
        return {}

    @expose('json:')
    def verify_phone(self, number, **kw):
        require_access(self.neighborhood, 'register')
        p = plugin.ProjectRegistrationProvider.get()
        result = p.verify_phone(c.user, number)
        request_id = result.pop('request_id', None)
        if request_id:
            session['phone_verification.request_id'] = request_id
            number_hash = utils.phone_number_hash(number)
            session['phone_verification.number_hash'] = number_hash
            session.save()
        if 'error' in result:
            result['error'] = markupsafe.Markup.escape(result['error'])
            result['error'] = h.really_unicode(result['error'])
        return result

    @expose('json:')
    def check_phone_verification(self, pin, **kw):
        require_access(self.neighborhood, 'register')
        p = plugin.ProjectRegistrationProvider.get()
        request_id = session.get('phone_verification.request_id')
        number_hash = session.get('phone_verification.number_hash')
        res = p.check_phone_verification(c.user, request_id, pin, number_hash)
        if 'error' in res:
            res['error'] = markupsafe.Markup.escape(res['error'])
            res['error'] = h.really_unicode(res['error'])
        return res

    @expose('json:')
    @validate(W.add_project)
    def check_names(self, **raw_data):
        require_access(self.neighborhood, 'register')
        return c.form_errors

    @h.vardec
    @expose()
    @validate(W.add_project, error_handler=add_project)
    @utils.AntiSpam.validate('Spambot protection engaged')
    @require_post()
    def register(
            self, project_unixname=None, project_description=None, project_name=None, neighborhood=None,
            private_project=None, tools=None, **kw):
        require_access(self.neighborhood, 'register')
        if private_project:
            require_access(self.neighborhood, 'admin')
        neighborhood = M.Neighborhood.query.get(name=neighborhood)

        project_description = h.really_unicode(project_description or '')
        project_name = h.really_unicode(project_name or '')
        project_unixname = h.really_unicode(project_unixname or '').lower()
        try:
            c.project = neighborhood.register_project(project_unixname,
                                                      project_name=project_name, private_project=private_project)
        except exceptions.ProjectOverlimitError:
            flash(
                "You have exceeded the maximum number of projects you are allowed to create", 'error')
            redirect('add_project')
        except exceptions.ProjectRatelimitError:
            flash(
                "Project creation rate limit exceeded.  Please try again later.", 'error')
            redirect('add_project')
        except exceptions.ProjectPhoneVerificationError:
            flash('You must pass phone verification', 'error')
            redirect('add_project')
        except Exception as e:
            log.error('error registering project: %s',
                      project_unixname, exc_info=True)
            flash('Internal Error. Please try again later.', 'error')
            redirect('add_project')

        if project_description:
            c.project.short_description = project_description
        offset = c.project.next_mount_point(include_hidden=True)
        if tools and not neighborhood.project_template:
            anchored_tools = neighborhood.get_anchored_tools()
            install_params = []
            for i, tool in enumerate(tools):
                if (tool.lower() not in list(anchored_tools.keys())) and (c.project.app_instance(tool) is None):
                    install_params.append(dict(ep_name=tool, ordinal=i + offset))
            c.project.install_apps(install_params)
        redirect(c.project.script_name + 'admin/?first-visit')

    @expose()
    def icon(self, w=None, **kw):
        try:
            if isinstance(w, list):
               w = w[0]
            icon = c.project.icon_sized(w=int(w or 48))
        except ValueError as e:
            log.info('Invalid project icon size: %s on %s', e, request.url)
            icon = None
        if icon is None and w is None:
            # fallback to older icons stored with neighborhood_id rather than using the nbhd project_id
            icon = self.neighborhood.icon
        if not icon:
            raise exc.HTTPNotFound
        return icon.serve()

    @expose('json:')
    def users(self, **kw):
        p = self.neighborhood.neighborhood_project
        return {
            'options': [{
                'value': u.username,
                'label': f'{u.display_name} ({u.username})'
            } for u in p.users()]
        }


class NeighborhoodProjectBrowseController(ProjectBrowseController):

    def __init__(self, neighborhood=None, category_name=None, parent_category=None):
        self.neighborhood = neighborhood
        super().__init__(
            category_name=category_name, parent_category=parent_category)
        self.nav_stub = '%sbrowse/' % self.neighborhood.url()
        self.additional_filters = {'neighborhood_id': self.neighborhood._id}

    @expose()
    def _lookup(self, category_name, *remainder):
        c.project = self.neighborhood.neighborhood_project
        category_name = unquote(category_name)
        return NeighborhoodProjectBrowseController(neighborhood=self.neighborhood, category_name=category_name, parent_category=self.category), remainder

    @expose('jinja:allura:templates/neighborhood_project_list.html')
    @without_trailing_slash
    def index(self, sort='alpha', limit=25, page=0, **kw):
        c.project_summary = W.project_summary
        c.page_list = W.page_list
        limit, page, start = g.handle_paging(limit, page)
        projects, count = self._find_projects(
            sort=sort, limit=limit, start=start)
        title = self._build_title()
        c.custom_sidebar_menu = self._build_nav()
        return dict(projects=projects,
                    title=title,
                    text=None,
                    neighborhood=self.neighborhood,
                    sort=sort,
                    limit=limit, page=page, count=count)


class ToolListController:

    """Renders a list of all tools of a given type in the current project."""

    @expose('jinja:allura:templates/tool_list.html')
    def _default(self, tool_name=None, page=0, limit=200, **kw):
        if tool_name is None:
            raise exc.HTTPNotFound
        c.page_list = W.page_list
        tool_name = tool_name.lower()
        entries = c.project.sitemap(included_tools=[tool_name],
                tools_only=True, per_tool_limit=None)
        total_entries = len(entries)
        limit, page = h.paging_sanitizer(limit, page, total_entries)
        start = page * limit
        tool_label = g.entry_points['tool'][tool_name].tool_label if entries else None
        return dict(
            page=page,
            limit=limit,
            total_entries=total_entries,
            entries=entries[start:start + limit],
            type=tool_label,
            tool_name=h.pluralize_tool_name(tool_label, total_entries),
            )


class ProjectController(FeedController):

    def __init__(self):
        self.screenshot = ScreenshotsController()
        self._list = ToolListController()

    @expose('json:')
    def _nav(self, admin_options=False, **kw):
        return c.project.nav_data(admin_options=admin_options)

    @expose()
    def _lookup(self, name, *remainder):
        name = unquote(name)
        name = six.ensure_text(name)  # we don't support unicode names, but in case a url comes in with one
        if name == '_nav.json':
            return self, ['_nav']

        if c.project.deleted:
            if c.user not in c.project.admins():
                raise exc.HTTPNotFound(name)
        app = c.project.app_instance(name)

        if app:
            c.app = app
            if app.root:
                return app.root, remainder
        subproject = M.Project.query.get(
            shortname=c.project.shortname + '/' + name,
            neighborhood_id=c.project.neighborhood_id)
        if subproject:
            c.project = subproject
            c.app = None
            return ProjectController(), remainder

        if c.project.is_nbhd_project:
            raise exc.HTTPNotFound(name)
        else:
            # if a tool under a project doesn't exist, redirect to the first valid tool instead of 404
            self.index()

    @expose('jinja:allura:templates/members.html')
    @with_trailing_slash
    def _members(self, **kw):
        users = []
        admins = []
        developers = []
        for user in c.project.users():
            roles = M.ProjectRole.query.find(
                {'_id': {'$in': M.ProjectRole.by_user(user).roles}})
            roles = {r.name for r in roles}
            _user = user
            _user['roles'] = ', '.join(sorted(roles))
            if 'Admin' in roles:
                admins.append(_user)
            elif 'Developer' in roles:
                developers.append(_user)
            else:
                users.append(_user)
        get_username = lambda user: user['username']
        admins = sorted(admins, key=get_username)
        developers = sorted(developers, key=get_username)
        users = sorted(users, key=get_username)
        return dict(users=admins + developers + users)

    def _check_security(self):
        require_access(c.project, 'read')

    @expose()
    def index(self, **kw):
        mount, app = c.project.first_mount_visible(c.user)
        if mount is not None:
            if hasattr(app, 'default_redirect'):
                app.default_redirect()
            args = dict(redirect_with=exc.HTTPMovedPermanently)
            redirect(app.url() if callable(app.url) else app.url, **args)  # Application has property; Subproject has method
        else:
            redirect(c.project.app_configs[0].url(), redirect_with=exc.HTTPMovedPermanently)

    def get_feed(self, project, app, user):
        """Return a :class:`allura.controllers.feed.FeedArgs` object describing
        the xml feed for this controller.

        Overrides :meth:`allura.controllers.feed.FeedController.get_feed`.

        """
        return FeedArgs(
            dict(project_id=project._id),
            'Recent changes to Project %s' % project.name,
            project.url())

    @expose()
    def icon(self, w=48, **kw):
        try:
            if isinstance(w, list):
               w = w[0]
            icon = c.project.icon_sized(w=int(w))
        except ValueError as e:
            log.info('Invalid project icon size: %s on %s', e, request.url)
            icon = None
        if not icon:
            raise exc.HTTPNotFound
        return icon.serve()

    @expose()
    def user_icon(self, **kw):
        try:
            return self.icon(**kw)
        except exc.HTTPNotFound:
            if config.get('default_avatar_image'):
                default_image_url = config['default_avatar_image']
            else:
                default_image_url = g.forge_static('images/user.png')
            redirect(default_image_url)

    @expose('json:')
    def user_search(self, term='', **kw):
        if len(term) < 3:
            raise exc.HTTPBadRequest('"term" param must be at least length 3')
        named_roles = RoleCache(
            g.credentials,
            g.credentials.project_roles(project_id=c.project.root_project._id).named)
        users = M.User.query.find({
            '_id': {'$in': named_roles.userids_that_reach},
            'display_name': re.compile(r'(?i)%s' % re.escape(term)),
            'disabled': False,
            'pending': False,
        }).sort('username').limit(10).all()
        return dict(
            users=[
                dict(
                    label='{} ({})'.format(u.get_pref('display_name'), u.username),
                    value=u.username,
                    id=u.username)
                for u in users])

    @expose('json:')
    def users(self, **kw):
        users = c.project.users()
        if c.user and c.user in users:
            users.remove(c.user)
            users.insert(0, c.user)

        return {
            'options': [{
                'value': u.username,
                'label': f'{u.display_name} ({u.username})'
            } for u in users]
        }


class ScreenshotsController:

    @expose()
    def _lookup(self, filename, *args):
        if args:
            filename = unquote(filename)
        else:
            filename = unquote(request.path.rsplit('/', 1)[-1])
        return ScreenshotController(filename), args


class ScreenshotController:

    def __init__(self, filename):
        self.filename = filename

    @expose()
    def index(self, embed=True, **kw):
        return self._screenshot.serve(embed)

    @expose()
    def thumb(self, embed=True, **kwargs):
        return self._thumb.serve(embed)

    @LazyProperty
    def _screenshot(self):
        f = M.ProjectFile.query.get(
            project_id=c.project._id,
            category='screenshot',
            filename=self.filename)
        if not f:
            raise exc.HTTPNotFound
        return f

    @LazyProperty
    def _thumb(self):
        f = M.ProjectFile.query.get(
            project_id=c.project._id,
            category='screenshot_thumb',
            filename=self.filename)
        if not f:
            raise exc.HTTPNotFound
        return f


def set_nav(neighborhood):
    project = neighborhood.neighborhood_project
    if project:
        c.project = project
        g.set_app('admin')
    else:
        admin_url = neighborhood.url() + '_admin/'
        c.custom_sidebar_menu = [
            SitemapEntry('Overview', admin_url + 'overview'),
            SitemapEntry('Awards', admin_url + 'accolades')]


class NeighborhoodAdminController:

    def __init__(self, neighborhood):
        self.neighborhood = neighborhood
        self.awards = NeighborhoodAwardsController(self.neighborhood)
        self.stats = NeighborhoodStatsController(self.neighborhood)

    def _check_security(self):
        require_access(self.neighborhood, 'admin')

    @with_trailing_slash
    @expose()
    def index(self, **kw):
        utils.permanent_redirect('overview')

    @without_trailing_slash
    @expose('jinja:allura:templates/neighborhood_admin_overview.html')
    def overview(self, **kw):
        set_nav(self.neighborhood)
        c.overview_form = W.neighborhood_overview_form
        allow_undelete = asbool(config.get('allow_project_undelete', True))
        allow_wiki_as_root = True if get_default_wiki_page() else False

        return dict(
            neighborhood=self.neighborhood,
            allow_project_undelete=allow_undelete,
            allow_wiki_as_root=allow_wiki_as_root)

    @without_trailing_slash
    @expose('jinja:allura:templates/neighborhood_admin_permissions.html')
    def permissions(self):
        set_nav(self.neighborhood)
        return dict(neighborhood=self.neighborhood)

    @expose('json:')
    def project_search(self, term='', **kw):
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
        set_nav(self.neighborhood)
        awards = M.Award.query.find(
            dict(created_by_neighborhood_id=self.neighborhood._id)).all()
        awards_count = len(awards)
        grants = M.AwardGrant.query.find(
            dict(granted_by_neighborhood_id=self.neighborhood._id))
        grants_count = grants.count()
        c.award_grant_form = W.award_grant_form(
            awards=awards,
            project_select_url=self.neighborhood.url() + '_admin/project_search')
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
        nbhd = self.neighborhood
        c.project = nbhd.neighborhood_project
        h.log_if_changed(nbhd, 'name', name,
                         'change neighborhood name to %s' % name)
        nbhd_redirect = kw.pop('redirect', '')
        h.log_if_changed(nbhd, 'redirect', nbhd_redirect,
                         'change neighborhood redirect to %s' % nbhd_redirect)
        h.log_if_changed(nbhd, 'homepage', homepage,
                         'change neighborhood homepage to %s' % homepage)
        h.log_if_changed(nbhd, 'css', css,
                         'change neighborhood css to %s' % css)
        h.log_if_changed(nbhd, 'project_template', project_template,
                         'change neighborhood project template to %s'
                         % project_template)
        allow_browse = kw.get('allow_browse', False)
        h.log_if_changed(nbhd, 'allow_browse', allow_browse,
                         'change neighborhood allow browse to %s'
                         % allow_browse)
        show_title = kw.get('show_title', False)
        h.log_if_changed(nbhd, 'show_title', show_title,
                         'change neighborhood show title to %s' % show_title)
        use_wiki_page_as_root = kw.get('use_wiki_page_as_root', False)
        h.log_if_changed(nbhd, 'use_wiki_page_as_root', use_wiki_page_as_root,
                         'change use wiki page as root to %s' % use_wiki_page_as_root)
        project_list_url = kw.get('project_list_url', '')
        h.log_if_changed(nbhd, 'project_list_url', project_list_url,
                         'change neighborhood project list url to %s'
                         % project_list_url)
        tracking_id = kw.get('tracking_id', '')
        h.log_if_changed(nbhd, 'tracking_id', tracking_id,
                         'update neighborhood tracking_id')
        prohibited_tools = kw.get('prohibited_tools', '')

        result = True
        if prohibited_tools.strip() != '':
            for prohibited_tool in prohibited_tools.split(','):
                if prohibited_tool.strip() not in g.entry_points['tool']:
                    flash('Prohibited tools "%s" is invalid' %
                          prohibited_tool.strip(), 'error')
                    result = False

        if result:
            h.log_if_changed(nbhd, 'prohibited_tools', prohibited_tools,
                             'update neighborhood prohibited tools')

        anchored_tools = kw.get('anchored_tools', '')
        validate_tools = dict()
        result = True
        if anchored_tools.strip() != '':
            try:
                validate_tools = {
                    tool.split(':')[0].lower(): tool.split(':')[1]
                    for tool in anchored_tools.replace(' ', '').split(',')}
            except Exception:
                flash('Anchored tools "%s" is invalid' %
                      anchored_tools, 'error')
                result = False

        for tool in validate_tools.keys():
            if tool not in g.entry_points['tool']:
                flash('Anchored tools "%s" is invalid' %
                      anchored_tools, 'error')
                result = False
        if result:
            h.log_if_changed(nbhd, 'anchored_tools', anchored_tools,
                             'update neighborhood anchored tools')

        if icon is not None and icon != b'':
            if self.neighborhood.icon:
                self.neighborhood.icon.delete()
                M.ProjectFile.query.remove(dict(project_id=c.project._id, category=re.compile(r'^icon')))
            save_icon = c.project.save_icon(icon.filename, icon.file, content_type=icon.type)
            if save_icon:
                M.AuditLog.log('update neighborhood icon')
            else:
                M.AuditLog.log('could not update neighborhood icon')
                flash("There's a problem with the uploaded image", 'error')
        redirect('overview')

    @expose('jinja:allura:templates/neighborhood_help.html')
    @with_trailing_slash
    def help(self, **kw):
        require_access(self.neighborhood, 'admin')
        set_nav(self.neighborhood)
        return dict(
            neighborhood=self.neighborhood,
        )


class NeighborhoodStatsController:

    def __init__(self, neighborhood):
        self.neighborhood = neighborhood

    @with_trailing_slash
    @expose('jinja:allura:templates/neighborhood_stats.html')
    def index(self, **kw):
        delete_count = M.Project.query.find(
            dict(neighborhood_id=self.neighborhood._id, deleted=True)).count()
        public_count = 0
        private_count = 0
        last_updated_30 = 0
        last_updated_60 = 0
        last_updated_90 = 0
        today_date = datetime.today()
        # arbitrary limit for efficiency
        if M.Project.query.find(dict(neighborhood_id=self.neighborhood._id, deleted=False)).count() < 20000:
            for p in M.Project.query.find(dict(neighborhood_id=self.neighborhood._id, deleted=False)):
                if p.private:
                    private_count = private_count + 1
                else:
                    public_count = public_count + 1
                    if today_date - p.last_updated < timedelta(days=30):
                        last_updated_30 = last_updated_30 + 1
                    if today_date - p.last_updated < timedelta(days=60):
                        last_updated_60 = last_updated_60 + 1
                    if today_date - p.last_updated < timedelta(days=90):
                        last_updated_90 = last_updated_90 + 1

        set_nav(self.neighborhood)
        return dict(
            delete_count=delete_count,
            public_count=public_count,
            private_count=private_count,
            last_updated_30=last_updated_30,
            last_updated_60=last_updated_60,
            last_updated_90=last_updated_90,
            neighborhood=self.neighborhood,
        )

    @without_trailing_slash
    @expose('jinja:allura:templates/neighborhood_stats_adminlist.html')
    def adminlist(self, sort='alpha', limit=25, page=0, **kw):
        limit, page, start = g.handle_paging(limit, page)

        pq = M.Project.query.find(
            dict(neighborhood_id=self.neighborhood._id, deleted=False))
        if sort == 'alpha':
            pq.sort('name')
        else:
            pq.sort('last_updated', pymongo.DESCENDING)
        count = pq.count()
        projects = pq.skip(start).limit(int(limit)).all()

        entries = []
        for proj in projects:
            admin_role = M.ProjectRole.query.get(
                project_id=proj.root_project._id, name='Admin')
            if admin_role is None:
                continue
            user_role_list = M.ProjectRole.query.find(
                dict(project_id=proj.root_project._id, name=None)).all()
            for ur in user_role_list:
                if ur.user is not None and admin_role._id in ur.roles:
                    entries.append({'project': proj, 'user': ur.user})

        set_nav(self.neighborhood)
        return dict(entries=entries,
                    sort=sort,
                    limit=limit, page=page, count=count,
                    page_list=W.page_list,
                    neighborhood=self.neighborhood,
                    )


class NeighborhoodModerateController:

    def __init__(self, neighborhood):
        self.neighborhood = neighborhood

    def _check_security(self):
        require_access(self.neighborhood, 'admin')

    @expose('jinja:allura:templates/neighborhood_moderate.html')
    def index(self, **kw):
        c.project = self.neighborhood.neighborhood_project
        other_nbhds = list(M.Neighborhood.query.find(
            dict(_id={'$ne': self.neighborhood._id})).sort('name'))
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
        p = M.Project.query.get(
            shortname=pid, neighborhood_id=self.neighborhood._id, deleted=False)
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


class NeighborhoodAwardsController:

    def __init__(self, neighborhood=None):
        if neighborhood is not None:
            self.neighborhood = neighborhood

    @expose('jinja:allura:templates/awards.html')
    def index(self, **kw):
        require_access(self.neighborhood, 'admin')
        awards = M.Award.query.find(
            dict(created_by_neighborhood_id=self.neighborhood._id)).all()
        return dict(awards=awards or [], count=len(awards))

    @expose('jinja:allura:templates/award_not_found.html')
    def not_found(self, **kw):
        return dict()

    @expose('jinja:allura:templates/grants.html')
    def grants(self, **kw):
        require_access(self.neighborhood, 'admin')
        grants = M.AwardGrant.query.find(
            dict(granted_by_neighborhood_id=self.neighborhood._id))
        count = grants.count()
        return dict(grants=grants or [], count=count)

    @expose()
    def _lookup(self, award_id, *remainder):
        return AwardController(self.neighborhood, award_id), remainder

    @expose()
    @require_post()
    def create(self, icon=None, short=None, full=None):
        require_access(self.neighborhood, 'admin')
        app_config_id = ObjectId()
        if short:
            award = M.Award(app_config_id=app_config_id)
            award.short = short
            award.full = full
            award.created_by_neighborhood_id = self.neighborhood._id
            if hasattr(icon, 'filename'):
                M.AwardFile.save_image(
                    icon.filename, icon.file, content_type=icon.type,
                    square=True, thumbnail_size=(48, 48),
                    thumbnail_meta=dict(award_id=award._id))
        redirect(six.ensure_text(request.referer or '/'))

    @expose()
    @require_post()
    def grant(self, grant=None, recipient=None, url=None, comment=None):
        require_access(self.neighborhood, 'admin')
        grant_q = M.Award.query.find(dict(short=grant,
                                          created_by_neighborhood_id=self.neighborhood._id)).first()
        recipient_q = M.Project.query.find(dict(
            neighborhood_id=self.neighborhood._id, shortname=recipient,
            deleted=False)).first()
        if grant_q and recipient_q:
            app_config_id = ObjectId()
            award = M.AwardGrant(app_config_id=app_config_id)
            award.award_id = grant_q._id
            award.granted_to_project_id = recipient_q._id
            award.granted_by_neighborhood_id = self.neighborhood._id
            award.award_url = url
            award.comment = comment
            with h.push_context(recipient_q._id):
                g.post_event('project_updated')
        redirect(six.ensure_text(request.referer or '/'))


class AwardController:

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
        recipient = unquote(recipient)
        return GrantController(self.neighborhood, self.award, recipient), remainder

    @expose()
    def icon(self, **kw):
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
                square=True, thumbnail_size=(48, 48),
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
        redirect(six.ensure_text(request.referer or '/'))


class GrantController:

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
    def icon(self, **kw):
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
        redirect(six.ensure_text(request.referer or '/'))


class ProjectImporterController:

    def __init__(self, neighborhood, *a, **kw):
        super().__init__(*a, **kw)
        self.neighborhood = neighborhood

    @expose()
    def _lookup(self, source=None, *rest):
        if source is None:
            raise exc.HTTPNotFound

        # iter_entry_points is a generator with 0 or 1 items, so a loop is the easiest way to handle
        for ep in iter_entry_points('allura.project_importers', source):
            return ep.load()(self.neighborhood), rest

        raise exc.HTTPNotFound


def get_default_wiki_page():
    """
    Gets the default home page from the default Wiki setup.
    """

    from forgewiki import model as WM
    wiki_page = None
    wiki_app = c.project.app_instance('wiki')
    if wiki_app:
        wiki_page = WM.Page.query.get(app_config_id=wiki_app.config._id, title='Home')
        return wiki_page
