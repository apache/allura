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

import logging
from collections import Counter, OrderedDict
from datetime import datetime
from copy import deepcopy
import urllib
import re
from xml.etree import ElementTree as ET

from tg import config
from pylons import tmpl_context as c, app_globals as g
from pylons import request
from paste.deploy.converters import asbool
import formencode as fe
import json
from webob import exc

from ming import schema as S
from ming.utils import LazyProperty
from ming.orm import ThreadLocalORMSession
from ming.orm import session, state, MapperExtension
from ming.orm import FieldProperty, RelationProperty, ForeignIdProperty
from ming.orm.declarative import MappedClass

from allura.lib import helpers as h
from allura.lib import plugin
from allura.lib import exceptions
from allura.lib import security
from allura.lib import validators as v
from allura.lib.security import has_access
from allura.lib.search import SearchIndexable
from allura.model.types import MarkdownCache

from .session import main_orm_session
from .session import project_orm_session
from .neighborhood import Neighborhood
from .auth import ProjectRole, User
from .timeline import ActivityNode, ActivityObject
from .types import ACL, ACE
from .monq_model import MonQTask

from filesystem import File

log = logging.getLogger(__name__)

# max sitemap entries per tool type
SITEMAP_PER_TOOL_LIMIT = 10


class ProjectFile(File):

    class __mongometa__:
        session = main_orm_session
        indexes = [('project_id', 'category')]

    project_id = FieldProperty(S.ObjectId)
    category = FieldProperty(str)
    caption = FieldProperty(str)
    sort = FieldProperty(int)


class ProjectCategory(MappedClass):

    class __mongometa__:
        session = main_orm_session
        name = 'project_category'

    _id = FieldProperty(S.ObjectId)
    parent_id = FieldProperty(S.ObjectId, if_missing=None)
    name = FieldProperty(str)
    label = FieldProperty(str, if_missing='')
    description = FieldProperty(str, if_missing='')

    @property
    def parent_category(self):
        return self.query.get(_id=self.parent_id)

    @property
    def subcategories(self):
        return self.query.find(dict(parent_id=self._id)).all()


class TroveCategoryMapperExtension(MapperExtension):

    def after_insert(self, obj, state, sess):
        g.post_event('trove_category_created', obj.trove_cat_id)

    def after_update(self, obj, state, sess):
        g.post_event('trove_category_updated', obj.trove_cat_id)

    def after_delete(self, obj, state, sess):
        g.post_event('trove_category_deleted', obj.trove_cat_id)


class TroveCategory(MappedClass):

    class __mongometa__:
        session = main_orm_session
        name = 'trove_category'
        extensions = [TroveCategoryMapperExtension]
        indexes = ['trove_cat_id', 'trove_parent_id', 'shortname', 'fullpath']

    _id = FieldProperty(S.ObjectId)
    trove_cat_id = FieldProperty(int, if_missing=None)
    trove_parent_id = FieldProperty(int, if_missing=None)
    shortname = FieldProperty(str, if_missing='')
    fullname = FieldProperty(str, if_missing='')
    fullpath = FieldProperty(str, if_missing='')
    parent_only = FieldProperty(bool, if_missing=False)
    show_as_skill = FieldProperty(bool, if_missing=True)

    @property
    def parent_category(self):
        return self.query.get(trove_cat_id=self.trove_parent_id)

    @property
    def subcategories(self):
        return self.query.find(dict(trove_parent_id=self.trove_cat_id)).sort('fullname').all()

    @property
    def children(self):
        return self.query.find({'fullpath': re.compile('^' + re.escape(self.fullpath) + ' ::')}).sort('fullpath')

    @property
    def type(self):
        trove = self
        while trove.trove_parent_id != 0:
            trove = trove.parent_category
        return trove.shortname

    @LazyProperty
    def ancestors(self):
        ancestors = []
        trove = self
        while trove:
            ancestors.append(trove)
            trove = trove.parent_category
        return ancestors

    @LazyProperty
    def breadcrumbs(self):
        url = '/directory/'
        crumbs = []
        for trove in reversed(self.ancestors[:-1]):
            url += trove.shortname + '/'
            crumbs.append((trove.fullname, url))
        return crumbs

    def __json__(self):
        return dict(
            id=self.trove_cat_id,
            shortname=self.shortname,
            fullname=self.fullname,
            fullpath=self.fullpath,
        )


class Project(SearchIndexable, MappedClass, ActivityNode, ActivityObject):
    '''
    Projects contain tools, subprojects, and their own metadata.  They live
    in exactly one :class:`~allura.model.neighborhood.Neighborhood`
    '''

    _perms_base = ['read', 'update', 'admin', 'create']
    _perms_init = _perms_base + ['register']

    class __mongometa__:
        session = main_orm_session
        name = 'project'
        indexes = [
            'name',
            'neighborhood_id',
            ('neighborhood_id', 'name'),
            'shortname',
            'parent_id',
            ('deleted', 'shortname', 'neighborhood_id'),
            ('neighborhood_id', 'is_nbhd_project', 'deleted')]
        unique_indexes = [('neighborhood_id', 'shortname')]

    type_s = 'Project'

    # Project schema
    _id = FieldProperty(S.ObjectId)
    parent_id = FieldProperty(S.ObjectId, if_missing=None)
    neighborhood_id = ForeignIdProperty(Neighborhood)
    shortname = FieldProperty(str)
    name = FieldProperty(str)
    show_download_button = FieldProperty(S.Deprecated)
    short_description = FieldProperty(str, if_missing='')
    summary = FieldProperty(str, if_missing='')
    description = FieldProperty(str, if_missing='')
    description_cache = FieldProperty(MarkdownCache)
    homepage_title = FieldProperty(str, if_missing='')
    external_homepage = FieldProperty(str, if_missing='')
    video_url = FieldProperty(str, if_missing='')
    support_page = FieldProperty(str, if_missing='')
    support_page_url = FieldProperty(str, if_missing='')
    socialnetworks = FieldProperty([dict(socialnetwork=str, accounturl=str)])
    removal = FieldProperty(str, if_missing='')
    moved_to_url = FieldProperty(str, if_missing='')
    removal_changed_date = FieldProperty(datetime, if_missing=datetime.utcnow)
    export_controlled = FieldProperty(bool, if_missing=False)
    export_control_type = FieldProperty(str, if_missing=None)
    database = FieldProperty(S.Deprecated)
    database_uri = FieldProperty(S.Deprecated)
    is_root = FieldProperty(bool)
    acl = FieldProperty(ACL(permissions=_perms_init))
    neighborhood_invitations = FieldProperty([S.ObjectId])
    neighborhood = RelationProperty(Neighborhood)
    app_configs = RelationProperty('AppConfig')
    category_id = FieldProperty(S.ObjectId, if_missing=None)
    deleted = FieldProperty(bool, if_missing=False)
    labels = FieldProperty([str])
    last_updated = FieldProperty(datetime, if_missing=None)
    tool_data = FieldProperty({str: {str: None}})  # entry point: prefs dict
    ordinal = FieldProperty(int, if_missing=0)
    database_configured = FieldProperty(bool, if_missing=True)
    _extra_tool_status = FieldProperty([str])
    trove_root_database = FieldProperty([S.ObjectId])
    trove_developmentstatus = FieldProperty([S.ObjectId])
    trove_audience = FieldProperty([S.ObjectId])
    trove_license = FieldProperty([S.ObjectId])
    trove_os = FieldProperty([S.ObjectId])
    trove_language = FieldProperty([S.ObjectId])
    trove_topic = FieldProperty([S.ObjectId])
    trove_natlanguage = FieldProperty([S.ObjectId])
    trove_environment = FieldProperty([S.ObjectId])
    tracking_id = FieldProperty(str, if_missing='')
    is_nbhd_project = FieldProperty(bool, if_missing=False)
    features = FieldProperty([str])

    # transient properties
    notifications_disabled = False

    @property
    def activity_name(self):
        return self.name

    @property
    def permissions(self):
        if self.shortname == '--init--':
            return self._perms_init
        else:
            return self._perms_base

    def parent_security_context(self):
        '''ACL processing should proceed up the project hierarchy.'''
        return self.parent_project

    @LazyProperty
    def allowed_tool_status(self):
        return ['production'] + self._extra_tool_status

    @h.exceptionless([], log)
    def sidebar_menu(self):
        from allura.app import SitemapEntry
        result = []
        if not self.is_root:
            p = self.parent_project
            result.append(SitemapEntry('Parent Project'))
            result.append(SitemapEntry(p.name or p.script_name, p.script_name))
        sps = self.direct_subprojects
        if sps:
            result.append(SitemapEntry('Child Projects'))
            result += [
                SitemapEntry(sp.name or sp.script_name, sp.script_name)
                for sp in sps]
        return result

    def troves_by_type(self, trove_type):
        troves = getattr(self, 'trove_%s' % trove_type)
        if troves:
            return TroveCategory.query.find({'_id': {'$in': troves}}).all()
        else:
            return []

    def all_troves(self):
        '''
        Returns a dict of human-readable root troves => [categories]
        '''
        troves = {}
        for attr in dir(self):
            if attr.startswith('trove_'):
                trove_type = attr.replace('trove_', '')
                nice_name = dict(
                    natlanguage='translation',
                    root_database='database',
                ).get(trove_type, trove_type)
                troves[nice_name] = self.troves_by_type(trove_type)
        return troves

    def get_tool_data(self, tool, key, default=None):
        return self.tool_data.get(tool, {}).get(key, default)

    def set_tool_data(self, tool, **kw):
        d = self.tool_data.setdefault(tool, {})
        d.update(kw)
        state(self).soil()

    def admin_menu(self):
        return []

    @property
    def script_name(self):
        url = self.url()
        if '//' in url:
            return url.rsplit('//')[-1]
        else:
            return url

    def url(self):
        if self.is_nbhd_project:
            return self.neighborhood.url()
        shortname = self.shortname[len(self.neighborhood.shortname_prefix):]
        url = self.neighborhood.url_prefix + shortname + '/'
        if url.startswith('//'):
            try:
                return request.scheme + ':' + url
            except TypeError:  # pragma no cover
                return 'http:' + url
        else:
            return url

    def best_download_url(self):
        provider = plugin.ProjectRegistrationProvider.get()
        return provider.best_download_url(self)

    def get_screenshots(self):
        return ProjectFile.query.find(dict(
            project_id=self._id,
            category='screenshot')).sort('sort').all()

    @LazyProperty
    def icon(self):
        return ProjectFile.query.get(
            project_id=self._id,
            category='icon')

    @property
    def description_html(self):
        return g.markdown.cached_convert(self, 'description')

    @property
    def parent_project(self):
        if self.is_root:
            return None
        return self.query.get(_id=self.parent_id)

    def _get_private(self):
        """Return True if this project is private, else False."""
        role_anon = ProjectRole.anonymous(project=self)
        return ACE.allow(role_anon._id, 'read') not in self.acl

    def _set_private(self, val):
        """Set whether this project is private or not."""
        new_val = bool(val)
        role_anon = ProjectRole.anonymous(project=self)
        ace = ACE.allow(role_anon._id, 'read')
        curr_val = ace not in self.acl
        if new_val == curr_val:
            return
        if new_val:
            self.acl.remove(ace)
        else:
            self.acl.append(ace)
    private = property(_get_private, _set_private)

    @property
    def is_user_project(self):
        return self.is_root and self.shortname.startswith('u/')

    @LazyProperty
    def user_project_of(self):
        '''
        If this is a user-project, return the User, else None
        '''
        user = None
        if self.is_user_project:
            user = plugin.AuthenticationProvider.get(
                request).user_by_project_shortname(self.shortname[2:])
        return user

    @LazyProperty
    def root_project(self):
        if self.is_root:
            return self
        return self.parent_project.root_project

    @LazyProperty
    def project_hierarchy(self):
        if not self.is_root:
            return self.root_project.project_hierarchy
        projects = set([self])
        while True:
            new_projects = set(
                self.query.find(dict(parent_id={'$in': [p._id for p in projects]})))
            new_projects.update(projects)
            if new_projects == projects:
                break
            projects = new_projects
        return projects

    @property
    def category(self):
        return ProjectCategory.query.find(dict(_id=self.category_id)).first()

    def roleids_with_permission(self, name):
        roles = set()
        for p in self.parent_iter():
            for ace in p.acl:
                if ace.permission == name and ace.access == ACE.allow:
                    roles.add(ace.role_id)
        return list(roles)

    @classmethod
    def menus(cls, projects):
        '''Return a dict[project_id] = sitemap of sitemaps, efficiently'''
        from allura.app import SitemapEntry
        pids = [p._id for p in projects]
        project_index = dict((p._id, p) for p in projects)
        entry_index = dict((pid, []) for pid in pids)
        q_subprojects = cls.query.find(dict(
            parent_id={'$in': pids},
            deleted=False))
        for sub in q_subprojects:
            entry_index[sub.parent_id].append(
                dict(ordinal=sub.ordinal, entry=SitemapEntry(sub.name, sub.url())))
        q_app_configs = AppConfig.query.find(dict(
            project_id={'$in': pids}))
        for ac in q_app_configs:
            App = ac.load()
            project = project_index[ac.project_id]
            app = App(project, ac)
            if app.is_visible_to(c.user):
                for sm in app.main_menu():
                    entry = sm.bind_app(app)
                    entry.ui_icon = 'tool-%s' % ac.tool_name
                    ordinal = ac.options.get('ordinal', 0)
                    entry_index[ac.project_id].append(
                        {'ordinal': ordinal, 'entry': entry})

        sitemaps = dict((pid, []) for pid in pids)
        for pid, entries in entry_index.iteritems():
            entries.sort(key=lambda e: e['ordinal'])
            sitemap = sitemaps[pid]
            for e in entries:
                sitemap.append(e['entry'])
        return sitemaps

    @classmethod
    def icon_urls(cls, projects):
        '''Return a dict[project_id] = icon_url, efficiently'''
        project_index = dict((p._id, p) for p in projects)
        result = dict((p._id, None) for p in projects)
        for icon in ProjectFile.query.find(dict(
                project_id={'$in': result.keys()},
                category='icon')):
            result[icon.project_id] = project_index[
                icon.project_id].url() + 'icon'
        return result

    @classmethod
    def accolades_index(cls, projects):
        '''Return a dict[project_id] = list of accolades, efficiently'''
        from .artifact import AwardGrant
        result = dict((p._id, []) for p in projects)
        for award in AwardGrant.query.find(dict(
                granted_to_project_id={'$in': result.keys()})):
            result[award.granted_to_project_id].append(award)
        return result

    def sitemap(self, excluded_tools=None, included_tools=None,
            tools_only=False, per_tool_limit=SITEMAP_PER_TOOL_LIMIT):
        """
        Return the project sitemap.

        :param list excluded_tools:
           Tool names (AppConfig.tool_name) to exclude from sitemap.

        :param list included_tools:
           Tool names (AppConfig.tool_name) to include. Use `None` to
           include all tool types.

        :param bool tools_only:
            Only include tools in the sitemap (exclude subprojects).

        :param int per_tool_limit:
            Max number of entries included in the sitemap for a single tool
            type. Use `None` to include all.

        """
        from allura.app import SitemapEntry
        entries = []

        anchored_tools = self.neighborhood.get_anchored_tools()
        i = len(anchored_tools)
        new_tools = self.install_anchored_tools()

        # Set menu mode
        delta_ordinal = i
        max_ordinal = i

        # Keep running count of entries per tool type
        tool_counts = Counter({tool_name: 0 for tool_name in g.entry_points['tool']})

        if not tools_only:
            for sub in self.direct_subprojects:
                ordinal = sub.ordinal + delta_ordinal
                if ordinal > max_ordinal:
                    max_ordinal = ordinal
                entries.append({'ordinal': sub.ordinal + delta_ordinal,
                               'entry': SitemapEntry(sub.name, sub.url())})

        for ac in self.app_configs + [a.config for a in new_tools]:
            if per_tool_limit:
                # We already have max entries for every tool type
                if min(tool_counts.values()) >= per_tool_limit:
                    break

                # We already have max entries for this tool type
                if tool_counts.get(ac.tool_name, 0) >= per_tool_limit:
                    continue

            if excluded_tools and ac.tool_name in excluded_tools:
                continue

            if included_tools and ac.tool_name not in included_tools:
                continue

            # Tool could've been uninstalled in the meantime
            try:
                App = ac.load()
            # If so, we don't want it listed
            except KeyError:
                log.exception('AppConfig %s references invalid tool %s',
                              ac._id, ac.tool_name)
                continue
            if getattr(c, 'app', None) and c.app.config._id == ac._id:
                # slight performance gain (depending on the app) by using the current app if we're on it
                app = c.app
            else:
                app = App(self, ac)
            if app.is_visible_to(c.user):
                for sm in app.main_menu():
                    entry = sm.bind_app(app)
                    entry.tool_name = ac.tool_name
                    entry.ui_icon = 'tool-%s' % entry.tool_name.lower()
                    if not self.is_nbhd_project and (entry.tool_name.lower() in anchored_tools.keys()):
                        ordinal = anchored_tools.keys().index(
                            entry.tool_name.lower())
                    elif ac.tool_name == 'admin':
                        ordinal = 100
                    else:
                        ordinal = int(ac.options.get('ordinal', 0)) + \
                            delta_ordinal
                    if self.is_nbhd_project and entry.label == 'Admin':
                        entry.matching_urls.append('%s_admin/' % self.url())
                    if ordinal > max_ordinal:
                        max_ordinal = ordinal
                    entries.append({'ordinal': ordinal, 'entry': entry})
                    tool_counts.update({ac.tool_name: 1})

        if (not tools_only and
                self == self.neighborhood.neighborhood_project and
                h.has_access(self.neighborhood, 'admin')):
            entries.append({
                'ordinal': max_ordinal + 1,
                'entry': SitemapEntry(
                    'Moderate',
                    "%s_moderate/" % self.neighborhood.url(),
                    ui_icon="tool-admin")
                })
            max_ordinal += 1

        entries = sorted(entries, key=lambda e: e['ordinal'])
        return [e['entry'] for e in entries]

    def install_anchored_tools(self):
        anchored_tools = self.neighborhood.get_anchored_tools()
        installed_tools = [tool.tool_name.lower() for tool in self.app_configs]
        i = 0
        new_tools = []
        if not self.is_nbhd_project:
            for tool, label in anchored_tools.iteritems():
                if (tool not in installed_tools) and (self.app_instance(tool) is None):
                    try:
                        new_tools.append(
                            self.install_app(tool, tool, label, i))
                    except Exception:
                        log.error('%s is not available' % tool, exc_info=True)
                i += 1
        return new_tools

    def nav_data(self, admin_options=False):
        from allura.ext.admin.admin_main import ProjectAdminRestController

        grouping_threshold = self.get_tool_data('allura', 'grouping_threshold', 1)
        anchored_tools = self.neighborhood.get_anchored_tools()
        children = []

        def make_entry(s, mount_point):
            entry = dict(name=s.label,
                         url=s.url,
                         icon=s.ui_icon or 'tool-admin',
                         tool_name=s.tool_name or 'sub',
                         mount_point=mount_point,
                         is_anchored=s.tool_name in anchored_tools.keys(),
                         )
            if admin_options and s.tool_name and mount_point:
                try:
                    entry['admin_options'] = ProjectAdminRestController().admin_options(mount_point)['options']
                except exc.HTTPError:
                    log.debug('Could not get admin_options mount_point for tool: %s', s.url)
            if admin_options and not s.tool_name:
                entry['admin_options'] = [dict(text='Subproject Admin', href=s.url + 'admin', className=None)]
            return entry

        for s in self.grouped_navbar_entries():
            if s.children:
                mount_point = None
            else:
                _offset = -2 if s.url.endswith("/") else -1
                mount_point = s.url.split('/')[_offset]
            entry = make_entry(s, mount_point=mount_point)
            if s.children:
                entry['children'] = [make_entry(child, mount_point=child.url.split('/')[-2]) for child in s.children]
            children.append(entry)

        response = dict(grouping_threshold=grouping_threshold, menu=children)

        if admin_options:
            _href = '{}admin/install_tool?tool_name={}'
            response['installable_tools'] = [dict(text=t['tool_label'],
                                                  href=_href.format(self.url(), t['name']),
                                                  tooltip=t['description'])
                                             for t in ProjectAdminRestController().installable_tools()['tools']]
        return response

    def grouped_navbar_entries(self):
        """Return a :class:`~allura.app.SitemapEntry` list suitable for rendering
        the project navbar with tools grouped together by tool type.
        """
        # get orginal (non-grouped) navbar entries
        sitemap = self.sitemap()
        # ordered dict to preserve the orginal ordering of tools
        grouped_nav = OrderedDict()
        # count how many tools of each type we have
        counts = Counter([e.tool_name.lower() for e in sitemap if e.tool_name])
        grouping_threshold = self.get_tool_data(
            'allura', 'grouping_threshold', 1)
        for e in sitemap:
            # if it's not a tool, add to navbar and continue
            if not e.tool_name:
                grouped_nav[id(e)] = e
                continue
            tool_name = e.tool_name.lower()
            if counts.get(tool_name, 1) <= grouping_threshold:
                # don't need grouping, so just add it directly
                grouped_nav[id(e)] = e
            else:
                # tool of a type we don't have in the navbar yet
                if tool_name not in grouped_nav:
                    child = deepcopy(e)
                    # change label to be the tool name (type)
                    e.label = g.entry_points['tool'][
                        tool_name].tool_label + u' \u25be'
                    # add tool url to list of urls that will match this nav entry
                    # have to do this before changing the url to the list page
                    e.matching_urls.append(e.url)
                    # change url to point to tool list page
                    e.url = self.url() + '_list/' + tool_name
                    e.children.append(child)
                    grouped_nav[tool_name] = e
                else:
                    # add tool url to list of urls that will match this nav
                    # entry
                    grouped_nav[tool_name].matching_urls.append(e.url)
                    if len(grouped_nav[tool_name].children) < SITEMAP_PER_TOOL_LIMIT - 1:
                        grouped_nav[tool_name].children.append(e)
                    elif len(grouped_nav[tool_name].children) == SITEMAP_PER_TOOL_LIMIT - 1:
                        e.url = self.url() + '_list/' + tool_name
                        e.label = 'More...'
                        grouped_nav[tool_name].children.append(e)
        return grouped_nav.values()

    def parent_iter(self):
        yield self
        pp = self.parent_project
        if pp:
            for p in pp.parent_iter():
                yield p

    @property
    def subprojects(self):
        q = self.query.find(dict(shortname={'$gt': self.shortname},
                                 neighborhood_id=self.neighborhood._id)).sort('shortname')
        for project in q:
            if project.shortname.startswith(self.shortname + '/'):
                yield project
            else:
                break

    @property
    def direct_subprojects(self):
        return self.query.find(dict(parent_id=self._id, deleted=False)).all()

    @property
    def accolades(self):
        from .artifact import AwardGrant
        return AwardGrant.query.find(dict(granted_to_project_id=self._id)).all()

    @property
    def named_roles(self):
        roles_ids = [r['_id']
                     for r in g.credentials.project_roles(self.root_project._id).named]
        roles = sorted(
            ProjectRole.query.find({'_id': {'$in': roles_ids}}),
            key=lambda r: r.name.lower())
        return roles

    def install_apps(self, apps_params):
        """ Install many apps at once.

        Better than doing individually if you expect
        default name conflicts (e.g. "code" for both git & svn), by using the
        tool_label value.

        :param list apps_params: list of dicts, where each dict is the args used in install_app()
        """

        # determine all the mount points
        mount_points = dict()
        for app_params in apps_params:
            App = g.entry_points['tool'][app_params['ep_name']]
            mount_point = self._mount_point_for_install(App, app_params.get('mount_point'))
            mount_points[App] = mount_point

        # count mount point names
        mount_point_counts = Counter(mount_points.values())

        # install each app with unique names
        for app_params in apps_params:
            App = g.entry_points['tool'][app_params['ep_name']]
            mount_point = mount_points[App]
            if mount_point_counts[mount_point] > 1:
                app_params.update(mount_point=App.tool_label.lower(),
                                  mount_label=App.tool_label)
            self.install_app(**app_params)

    def _mount_point_for_install(self, App, mount_point):
        with h.push_config(c, project=self):
            try:
                return v.MountPointValidator(App).to_python(mount_point)
            except fe.Invalid as e:
                raise exceptions.ToolError(str(e))

    def _validate_tool_option(self, opt, value):
        try:
            return opt.validate(value)
        except fe.Invalid as e:
            raise exceptions.ToolError(u'{}: {}'.format(opt.name, str(e)))

    def last_ordinal_value(self):
        last_menu_item = self.ordered_mounts(include_hidden=True)[-1]
        if 'ac' in last_menu_item:
            ordinal = last_menu_item['ac'].options.ordinal
        else:
            ordinal = last_menu_item['sub'].ordinal
        return ordinal

    def mount_points_generator(self):
        for item in self.ordered_mounts(include_hidden=True):
            if 'ac' in item:
                yield item['ac'].options.mount_point
            else:
                yield item['sub'].shortname

    def mount_points(self):
        return list(self.mount_points_generator())

    def install_app(self, ep_name, mount_point=None, mount_label=None, ordinal=None, **override_options):
        '''
        Install an app

        :param str ep_name: Entry Point name, e.g. "wiki"
        :param str mount_point: URL path, e.g. "docs"
        :param str mount_label: Display name
        :param int ordinal: location of tool, relative to others; None will go to the end.
        :param override_options:
        :return:
        '''
        App = g.entry_points['tool'][ep_name]
        mount_point = self._mount_point_for_install(App, mount_point)
        if ordinal is None:
            ordinal = self.last_ordinal_value() + 1
        options = App.default_options()
        options['mount_point'] = mount_point
        options['mount_label'] = mount_label or App.default_mount_label or mount_point
        options['ordinal'] = int(ordinal)
        options_on_install = {o.name: o for o in App.options_on_install()}
        for o, val in override_options.iteritems():
            if o in options_on_install:
                val = self._validate_tool_option(options_on_install[o], val)
            options[o] = val
        cfg = AppConfig(
            project_id=self._id,
            tool_name=ep_name.lower(),
            options=options)
        app = App(self, cfg)
        with h.push_config(c, project=self, app=app):
            session(cfg).flush()
            app.install(self)
        return app

    def uninstall_app(self, mount_point):
        app = self.app_instance(mount_point)
        if app is None:
            return
        if self.support_page == app.config.options.mount_point:
            self.support_page = ''
        with h.push_config(c, project=self, app=app):
            app.uninstall(self)

    def app_instance(self, mount_point_or_config):
        if isinstance(mount_point_or_config, AppConfig):
            app_config = mount_point_or_config
        else:
            app_config = self.app_config(mount_point_or_config)
        if app_config is None:
            return None
        App = app_config.load()
        if App is None:  # pragma no cover
            return None
        else:
            return App(self, app_config)

    def app_config(self, mount_point):
        return AppConfig.query.find({
            'project_id': self._id,
            'options.mount_point': mount_point}).first()

    def app_config_by_tool_type(self, tool_type):
        for ac in self.app_configs:
            if ac.tool_name == tool_type:
                return ac

    def new_subproject(self, name, install_apps=True, user=None, project_name=None):
        provider = plugin.ProjectRegistrationProvider.get()
        try:
            provider.shortname_validator.to_python(
                name, check_allowed=False, neighborhood=self.neighborhood)
        except exceptions.Invalid:
            raise exceptions.ToolError, 'Mount point "%s" is invalid' % name
        return provider.register_subproject(self, name, user or c.user, install_apps, project_name=project_name)

    def ordered_mounts(self, include_hidden=False):
        '''
        Returns an array of a projects mounts (tools and sub-projects) in toolbar order.
        Note that the top-level 'ordinal' field may be offset from the stored ordinal value, due to anchored tools
        '''
        result = []
        anchored_tools = self.neighborhood.get_anchored_tools()
        i = len(anchored_tools)
        self.install_anchored_tools()

        for sub in self.direct_subprojects:
            result.append(
                {'ordinal': int(sub.ordinal + i), 'sub': sub})
        for ac in self.app_configs:
            App = g.entry_points['tool'].get(ac.tool_name)
            if include_hidden or App and not App.hidden:
                if not self.is_nbhd_project and (ac.tool_name.lower() in anchored_tools.keys()):
                    ordinal = anchored_tools.keys().index(ac.tool_name.lower())
                else:
                    ordinal = int(ac.options.get('ordinal', 0)) + i
                result.append({'ordinal': int(ordinal), 'ac': ac})

        return sorted(result, key=lambda e: (e['ordinal']))

    def first_mount_visible(self, user):
        mounts = self.ordered_mounts()
        for mount in mounts:
            if 'sub' in mount:
                sub = mount['sub']
                if has_access(sub, 'read', user):
                    return mount
            elif 'ac' in mount:
                app = self.app_instance(mount['ac'])
                if app.is_visible_to(user):
                    return mount
        return None

    def next_mount_point(self, include_hidden=False):
        '''Return the ordinal of the next open toolbar mount point for this
        project.'''
        ordered_mounts = self.ordered_mounts(include_hidden=include_hidden)
        return int(ordered_mounts[-1]['ordinal']) + 1 \
            if ordered_mounts else 0

    def delete(self):
        # Cascade to subprojects
        for sp in self.direct_subprojects:
            sp.delete()
        # Cascade to app configs
        for ac in self.app_configs:
            self.uninstall_app(ac.options.get('mount_point'))
        MappedClass.delete(self)

    def breadcrumbs(self):
        if self.is_user_project:
            entry = (self.user_project_of.display_name, self.url())
        else:
            entry = (self.name, self.url())
        if self.parent_project:
            return self.parent_project.breadcrumbs() + [entry]
        else:
            return [(self.neighborhood.name, self.neighborhood.url())] + [entry]

    def users(self):
        '''Find all the users who have named roles for this project'''
        named_roles = security.RoleCache(
            g.credentials,
            g.credentials.project_roles(project_id=self.root_project._id).named)
        uids = [uid for uid in named_roles.userids_that_reach if uid is not None]
        return list(User.query.find({'_id': {'$in': uids}, 'disabled': False, 'pending': False}))

    def users_with_role(self, *role_names):
        """Return all users in this project that have at least one of the roles
        specified.

        e.g., project.users_with_role('Admin', 'Developer') -> returns all
          users in `project` having the Admin role or the Developer role, or both
        """
        users = set()
        for role_name in role_names:
            for user in g.credentials.users_with_named_role(self.root_project._id, role_name):
                if not user.disabled:
                    users.add(user)
        return list(users)

    def admins(self):
        """Find all the users who have 'Admin' role for this project"""
        return self.users_with_role('Admin')

    def user_in_project(self, username):
        from .auth import User
        u = User.by_username(username)
        if not u:
            return None
        named_roles = g.credentials.project_roles(
            project_id=self.root_project._id).named
        for r in named_roles.roles_that_reach:
            if r.get('user_id') == u._id:
                return u
        return None

    def configure_project(
            self,
            users=None, apps=None,
            is_user_project=False,
            is_private_project=False):
        from allura import model as M

        self.notifications_disabled = True
        if users is None:
            users = [c.user]
        if apps is None:
            apps = []
            if is_user_project:
                apps += [('Wiki', 'wiki', 'Wiki'),
                         ('profile', 'profile', 'Profile'),
                         ]
            apps += [
                ('admin', 'admin', 'Admin'),
                ('search', 'search', 'Search'),
            ]
            if asbool(config.get('activitystream.enabled', False)):
                apps.append(('activity', 'activity', 'Activity'))
        with h.push_config(c, project=self, user=users[0]):
            # Install default named roles (#78)
            root_project_id = self.root_project._id
            role_admin = M.ProjectRole.upsert(
                name='Admin', project_id=root_project_id)
            role_developer = M.ProjectRole.upsert(
                name='Developer', project_id=root_project_id)
            role_member = M.ProjectRole.upsert(
                name='Member', project_id=root_project_id)
            role_auth = M.ProjectRole.upsert(
                name='*authenticated', project_id=root_project_id)
            role_anon = M.ProjectRole.upsert(
                name='*anonymous', project_id=root_project_id)
            # Setup subroles
            role_admin.roles = [role_developer._id]
            role_developer.roles = [role_member._id]
            self.acl = [
                ACE.allow(role_developer._id, 'read'),
                ACE.allow(role_member._id, 'read')]
            self.acl += [
                M.ACE.allow(role_admin._id, perm)
                for perm in self.permissions]
            self.private = is_private_project
            for user in users:
                pr = ProjectRole.by_user(user, project=self, upsert=True)
                pr.roles = [role_admin._id]
            session(self).flush(self)
            # Setup apps
            for i, (ep_name, mount_point, label) in enumerate(apps):
                self.install_app(ep_name, mount_point, label, ordinal=i)
            self.database_configured = True
            self.notifications_disabled = False
            ThreadLocalORMSession.flush_all()

    def add_user(self, user, role_names):
        'Convenience method to add member with the given role(s).'
        pr = ProjectRole.by_user(user, project=self, upsert=True)
        for role_name in role_names:
            r = ProjectRole.by_name(role_name, self)
            pr.roles.append(r._id)

    @property
    def twitter_handle(self):
        return self.social_account('Twitter').accounturl

    @property
    def facebook_page(self):
        return self.social_account('Facebook').accounturl

    def social_account(self, socialnetwork):
        try:
            account = (
                sn for sn in self.socialnetworks if sn.socialnetwork == socialnetwork).next()
        except StopIteration:
            return None
        else:
            return account

    def set_social_account(self, socialnetwork, accounturl):
        account = self.social_account(socialnetwork)
        if account:
            account.accounturl = accounturl
        else:
            self.socialnetworks.append(dict(
                socialnetwork=socialnetwork,
                accounturl=accounturl
            ))

    def bulk_export_path(self):
        shortname = self.shortname
        if self.is_nbhd_project:
            shortname = self.url().strip('/')
        elif self.is_user_project:
            shortname = self.shortname.split('/')[1]
        elif not self.is_root:
            shortname = self.shortname.split('/')[0]
        return config['bulk_export_path'].format(
            nbhd=self.neighborhood.url_prefix.strip('/'),
            project=shortname,
            c=c,
        )

    def bulk_export_filename(self):
        '''
        Return a filename (configurable) for this project export.  The current timestamp
        may be included, so only run this method once per export.
        '''
        shortname = self.shortname
        if self.is_nbhd_project:
            shortname = self.url().strip('/')
        elif self.is_user_project:
            shortname = self.shortname.split('/')[1]
        elif not self.is_root:
            shortname = self.shortname.split('/')[1]

        return config['bulk_export_filename'].format(project=shortname, date=datetime.utcnow())

    def bulk_export_status(self):
        '''
        Returns 'busy' if an export is queued or in-progress.  Returns None otherwise
        '''
        q = {
            'task_name': 'allura.tasks.export_tasks.bulk_export',
            'state': {'$in': ['busy', 'ready']},
            'context.project_id': self._id,
        }
        export_task = MonQTask.query.get(**q)
        if not export_task:
            return
        else:
            return 'busy'

    def index(self):
        provider = plugin.ProjectRegistrationProvider.get()
        try:
            _private = self.private
        except Exception:
            log.warn('Error getting self.private on project {}'.format(self.shortname), exc_info=True)
            _private = False
        fields = dict(id=self.index_id(),
                      title='Project %s' % self.name,
                      type_s=self.type_s,
                      deleted_b=self.deleted,
                      # Not analyzed fields
                      private_b=_private,
                      neighborhood_id_s=str(self.neighborhood_id),
                      url_s=self.url(),
                      is_root_b=self.is_root,
                      is_nbhd_project_b=self.is_nbhd_project,
                      registration_dt=plugin.ProjectRegistrationProvider.get().registration_date(self),
                      removal_changed_date_dt=self.removal_changed_date,
                      name_t=self.name,
                      shortname_s=self.shortname,
                      neighborhood_name_s=self.neighborhood.name,
                      external_homepage_s=self.external_homepage,
                      # Analyzed fields
                      short_description_t=self.short_description,
                      labels_t=' '.join(self.labels),
                      summary_t=self.summary,
                      category_name_t=self.category.name if self.category else None,
                      category_description_t=self.category.description if self.category else None,
                      )
        return dict(provider.index_project(self), **fields)

    def should_update_index(self, old_doc, new_doc):
        """Skip index update if only `last_updated` has changed.

        Value of `last_updated` is updated whenever any artifact
        that belongs to project is changed. This generates a lot of
        unnecessary `add_projects` tasks for every simple user action.
        """
        old_doc.pop('last_updated', None)
        new_doc.pop('last_updated', None)
        return old_doc != new_doc

    def __json__(self):
        result = dict(
            shortname=self.shortname,
            name=self.name,
            _id=str(self._id),
            url=h.absurl(self.url()),
            private=self.private,
            short_description=self.short_description,
            creation_date=plugin.ProjectRegistrationProvider.get().registration_date(self).strftime('%Y-%m-%d'),
            summary=self.summary,
            external_homepage=self.external_homepage,
            video_url=self.video_url,
            socialnetworks=[dict(n) for n in self.socialnetworks],
            status=self.removal or 'active',
            moved_to_url=self.moved_to_url,
            preferred_support_tool=self.support_page,
            preferred_support_url=self.support_page_url,
            developers=[u.__json__()
                        for u in self.users_with_role('Developer')],
            tools=[self.app_instance(t) for t in self.app_configs if h.has_access(t, 'read')],
            labels=list(self.labels),
            categories={n: [t.__json__() for t in ts]
                        for n, ts in self.all_troves().items()},
            icon_url=h.absurl(self.url() + 'icon') if self.icon else None,
            screenshots=[
                dict(
                    url=h.absurl(self.url() + 'screenshot/' +
                                 urllib.quote(ss.filename.encode('utf8'))),
                    thumbnail_url=h.absurl(
                        self.url(
                        ) + 'screenshot/' + urllib.quote(ss.filename.encode('utf8')) + '/thumb'),
                    caption=ss.caption,
                )
                for ss in self.get_screenshots()
            ]
        )
        if self.is_user_project:
            result['profile_api_url'] = h.absurl('/rest' + self.url() + 'profile/')
        return result

    def doap(self):
        root = ET.Element('rdf:RDF', {
            'xmlns:rdf': "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            'xmlns:rdfs': "http://www.w3.org/2000/01/rdf-schema#",
        })
        project = ET.SubElement(root, 'Project', {
            'xmlns': "http://usefulinc.com/ns/doap#",
            'xmlns:foaf': "http://xmlns.com/foaf/0.1/",
            'xmlns:sf': "http://sourceforge.net/api/sfelements.rdf#",
            'xmlns:rss': "http://purl.org/rss/1.0/",
            'xmlns:dc': "http://dublincore.org/documents/dcmi-namespace/",
            'xmlns:beer': "http://www.purl.org/net/ontology/beer.owl#",
            'rdf:about': h.absurl('/rest/' + self.url().strip('/') + '?doap#'),
        })
        # Basic fields
        ET.SubElement(project, 'name').text = self.shortname
        ET.SubElement(project, 'dc:title').text = self.name
        ET.SubElement(project, 'sf:private').text = '1' if self.private else '0'  # strange, but sf.net does this
        ET.SubElement(project, 'shortdesc', {'xml:lang': 'en'}).text = self.summary
        ET.SubElement(project, 'description', {'xml:lang': 'en'}).text = self.short_description
        registration_date = plugin.ProjectRegistrationProvider.get().registration_date(self)
        ET.SubElement(project, 'created').text = registration_date.strftime('%Y-%m-%d')
        if self.external_homepage:
            ET.SubElement(project, 'homepage', {'rdf:resource': self.external_homepage})

        # Categories
        for cat in TroveCategory.query.find({'_id': {'$in': self.trove_audience}}):
            ET.SubElement(project, 'audience').text = cat.fullname
        for cat in TroveCategory.query.find({'_id': {'$in': self.trove_os}}):
            ET.SubElement(project, 'os').text = cat.fullname
        for cat in TroveCategory.query.find({'_id': {'$in': self.trove_language}}):
            ET.SubElement(project, 'programming-language').text = cat.fullname
        for cat in TroveCategory.query.find({'_id': {'$in': self.trove_license}}):
            ET.SubElement(project, 'license').text = cat.fullname
        for cat in TroveCategory.query.find({'_id': {'$in': self.trove_environment}}):
            ET.SubElement(project, 'sf:environment').text = cat.fullname
        for cat in TroveCategory.query.find({'_id': {'$in': self.trove_root_database}}):
            ET.SubElement(project, 'sf:database').text = cat.fullname
        all_troves = (
            self.trove_root_database +
            self.trove_developmentstatus +
            self.trove_audience +
            self.trove_license +
            self.trove_topic +
            self.trove_os +
            self.trove_language +
            self.trove_natlanguage +
            self.trove_environment
        )
        for cat in TroveCategory.query.find({'_id': {'$in': all_troves}}):
            ET.SubElement(project, 'category', {'rdf:resource': 'http://sourceforge.net/api/trove/index/rdf#%s' % cat.trove_cat_id})

        # Awards
        for a in self.accolades:
            award = ET.SubElement(project, 'sf:awarded')
            award = ET.SubElement(award, 'beer:Award')
            ET.SubElement(award, 'beer:awardCategory').text = a.award.full
            ET.SubElement(award, 'beer:awardedAt').text = a.granted_by_neighborhood.name

        # Maintainers
        admins = self.admins()
        for u in admins:
            person = ET.SubElement(project, 'maintainer')
            person = ET.SubElement(person, 'foaf:Person', {
                'xmlns:foaf': "http://xmlns.com/foaf/0.1/",
                'xmlns:rdf': "http://www.w3.org/1999/02/22-rdf-syntax-ns#"})
            ET.SubElement(person, 'foaf:name').text = u.display_name
            ET.SubElement(person, 'foaf:nick').text = u.username
            ET.SubElement(person, 'foaf:homepage', {'rdf:resource': h.absurl(u.url())})

        # Developers
        devs = [u for u in self.users_with_role('Developer') if u not in admins]
        for u in devs:
            person = ET.SubElement(project, 'developer')
            person = ET.SubElement(person, 'foaf:Person', {
                'xmlns:foaf': "http://xmlns.com/foaf/0.1/",
                'xmlns:rdf': "http://www.w3.org/1999/02/22-rdf-syntax-ns#"})
            ET.SubElement(person, 'foaf:name').text = u.display_name
            ET.SubElement(person, 'foaf:nick').text = u.username
            ET.SubElement(person, 'foaf:homepage', {'rdf:resource': h.absurl(u.url())})

        # Basic tool info
        apps = [self.app_instance(ac) for ac in self.app_configs if h.has_access(ac, 'read')]
        for app in apps:
            app.doap(project)

        return ET.tostring(root, encoding='utf-8')


class AppConfig(MappedClass, ActivityObject):

    """
    Configuration information for an instantiated :class:`Application <allura.app.Application>`
    in a :class:`Project`

    :var options: an object on which various options are stored.  options.mount_point is the url component for this app instance
    :var acl: a dict that maps permissions (strings) to lists of roles that have the permission
    """

    class __mongometa__:
        session = project_orm_session
        name = 'config'
        indexes = [
            'project_id',
            'options.import_id',
            ('options.mount_point', 'project_id')]

    # AppConfig schema
    _id = FieldProperty(S.ObjectId)
    project_id = ForeignIdProperty(Project)
    discussion_id = ForeignIdProperty('Discussion')
    tool_name = FieldProperty(str)
    version = FieldProperty(str)
    options = FieldProperty(None)
    project = RelationProperty(Project, via='project_id')
    discussion = RelationProperty('Discussion', via='discussion_id')
    tool_data = FieldProperty({str: {str: None}})  # entry point: prefs dict

    acl = FieldProperty(ACL())

    @property
    def activity_name(self):
        return self.options.mount_label

    def get_tool_data(self, tool, key, default=None):
        return self.tool_data.get(tool, {}).get(key, default)

    def set_tool_data(self, tool, **kw):
        d = self.tool_data.setdefault(tool, {})
        d.update(kw)
        state(self).soil()

    def parent_security_context(self):
        '''ACL processing should terminate at the AppConfig'''
        return None

    def load(self):
        """
        :returns: the related :class:`Application <allura.app.Application>` class
        """
        try:
            result = self._loaded_ep
        except AttributeError:
            result = self._loaded_ep = g.entry_points['tool'][self.tool_name]
        return result

    def script_name(self):
        return self.project.script_name + self.options.mount_point + '/'

    def url(self, project=None):
        'return the URL for the app config.  project parameter is for optimization'
        if not project:
            project = self.project
        return project.url() + self.options.mount_point + '/'

    def breadcrumbs(self):
        return self.project.breadcrumbs() + [
            (self.options.mount_point, self.url())]

    def __json__(self):
        options = self.options._deinstrument()
        options['url'] = self.project.url() + self.options.mount_point + '/'
        return dict(
            _id=self._id,
            # strip away the ming instrumentation
            options=options,
        )
