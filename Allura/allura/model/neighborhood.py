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
import json
import logging
from collections import OrderedDict
import typing

from ming import schema as S
from ming.orm import FieldProperty, RelationProperty
from ming.orm.declarative import MappedClass
from ming.utils import LazyProperty

from tg import request
from tg import tmpl_context as c, app_globals as g

from allura.lib import plugin

from .session import main_orm_session
from .filesystem import File
from .types import MarkdownCache

if typing.TYPE_CHECKING:
    from ming.odm.mapper import Query


log = logging.getLogger(__name__)


class NeighborhoodFile(File):

    class __mongometa__:
        session = main_orm_session
        indexes = ['neighborhood_id']

    query: 'Query[NeighborhoodFile]'

    neighborhood_id = FieldProperty(S.ObjectId)


re_picker_css_type = re.compile(r'^/\*(.+)\*/')
re_font_project_title = re.compile(r'font-family:(.+);}')
re_color_project_title = re.compile(r'color:(.+);}')
re_bgcolor_barontop = re.compile(r'background-color:([^;}]+);')
re_bgcolor_titlebar = re.compile(r'background-color:([^;}]+);')
re_color_titlebar = re.compile(r'color:([^;}]+);')


class Neighborhood(MappedClass):

    '''Provide a grouping of related projects.

    url_prefix - location of neighborhood (may include scheme and/or host)
    css - block of CSS text to add to all neighborhood pages
    '''
    class __mongometa__:
        session = main_orm_session
        name = 'neighborhood'
        unique_indexes = ['url_prefix']

    query: 'Query[Neighborhood]'

    _id = FieldProperty(S.ObjectId)
    name = FieldProperty(str)
    # e.g. http://adobe.openforge.com/ or projects/
    url_prefix = FieldProperty(str)
    shortname_prefix = FieldProperty(str, if_missing='')
    css = FieldProperty(str, if_missing='')
    homepage = FieldProperty(str, if_missing='')
    homepage_cache = FieldProperty(MarkdownCache)
    redirect = FieldProperty(str, if_missing='')
    projects = RelationProperty('Project')
    allow_browse = FieldProperty(bool, if_missing=True)
    show_title = FieldProperty(bool, if_missing=True)
    site_specific_html = FieldProperty(str, if_missing='')
    project_template = FieldProperty(str, if_missing='')
    tracking_id = FieldProperty(str, if_missing='')
    project_list_url = FieldProperty(str, if_missing='')
    level = FieldProperty(S.Deprecated)
    allow_private = FieldProperty(S.Deprecated)
    features = FieldProperty(dict(
        private_projects=bool,
        max_projects=S.Int,
        css=str,
        google_analytics=bool))
    anchored_tools = FieldProperty(str, if_missing='')
    prohibited_tools = FieldProperty(str, if_missing='')
    use_wiki_page_as_root = FieldProperty(bool, if_missing=False)

    def parent_security_context(self):
        return None

    @LazyProperty
    def neighborhood_project(self):
        from .project import Project
        p = Project.query.get(
            neighborhood_id=self._id,
            is_nbhd_project=True)
        assert p
        return p

    @property
    def acl(self):
        return self.neighborhood_project.acl

    @property
    def shortname(self):
        return self.url_prefix.strip('/')

    def url(self):
        url = self.url_prefix
        if url.startswith('//'):
            try:
                return request.scheme + ':' + url
            except TypeError:  # pragma no cover
                return 'http:' + url
        else:
            return url

    @LazyProperty
    def projects_count(self):
        from allura import model as M
        from allura.lib import helpers as h

        q = dict(
            deleted=False,
            is_nbhd_project=False,
            neighborhood_id=self._id)

        total = 0

        for p in M.Project.query.find(q):
            if h.has_access(p, 'read')():
                total = total + 1
                if total == 100:
                    return total

        return total

    def register_project(self, shortname, user=None, project_name=None, user_project=False, private_project=False,
                         apps=None, omit_event=False, **kwargs):
        '''Register a new project in the neighborhood.  The given user will
        become the project's superuser.  If no user is specified, c.user is used.
        '''
        provider = plugin.ProjectRegistrationProvider.get()
        if project_name is None:
            project_name = shortname
        return provider.register_project(self, shortname, project_name, user or getattr(c, 'user', None), user_project,
                                         private_project, apps, omit_event=omit_event, **kwargs)

    def get_custom_css(self):
        if self.allow_custom_css:
            return self.css
        return ""

    @property
    def has_home_tool(self):
        return (self.neighborhood_project
                    .app_config_by_tool_type('home') is not None)

    @LazyProperty
    def icon(self):
        # New icon storage uses the neighborhood_project object, so Project.icon* methods can be shared
        if self.neighborhood_project.get_tool_data('allura', 'icon_original_size'):
            icon = self.neighborhood_project.icon
        else:
            # fallback to older storage location
            icon = NeighborhoodFile.query.get(neighborhood_id=self._id)
        return icon

    @property
    def allow_custom_css(self):
        return self.features['css'] == 'custom' or self.features['css'] == 'picker'

    def get_project_template(self):
        if self.project_template:
            return json.loads(self.project_template)
        return {}

    def get_max_projects(self):
        return self.features['max_projects']

    def get_css_for_picker(self):
        projecttitlefont = {'label': 'Project title, font',
                            'name': 'projecttitlefont', 'value': '', 'type': 'font'}
        projecttitlecolor = {'label': 'Project title, color',
                             'name': 'projecttitlecolor', 'value': '', 'type': 'color'}
        barontop = {'label': 'Bar on top', 'name':
                    'barontop', 'value': '', 'type': 'color'}
        titlebarbackground = {'label': 'Title bar, background',
                              'name': 'titlebarbackground', 'value': '', 'type': 'color'}
        titlebarcolor = {
            'label': 'Title bar, foreground', 'name': 'titlebarcolor', 'value': '', 'type': 'color'}

        if self.css is not None:
            for css_line in self.css.split('\n'):
                m = re_picker_css_type.search(css_line)
                if not m:
                    continue

                css_type = m.group(1)
                if css_type == "projecttitlefont":
                    m = re_font_project_title.search(css_line)
                    if m:
                        projecttitlefont['value'] = m.group(1)

                elif css_type == "projecttitlecolor":
                    m = re_color_project_title.search(css_line)
                    if m:
                        projecttitlecolor['value'] = m.group(1)

                elif css_type == "barontop":
                    m = re_bgcolor_barontop.search(css_line)
                    if m:
                        barontop['value'] = m.group(1)

                elif css_type == "titlebarbackground":
                    m = re_bgcolor_titlebar.search(css_line)
                    if m:
                        titlebarbackground['value'] = m.group(1)

                elif css_type == "titlebarcolor":
                    m = re_color_titlebar.search(css_line)
                    if m:
                        titlebarcolor['value'] = m.group(1)

        styles_list = []
        styles_list.append(projecttitlefont)
        styles_list.append(projecttitlecolor)
        styles_list.append(barontop)
        styles_list.append(titlebarbackground)
        styles_list.append(titlebarcolor)
        return styles_list

    @staticmethod
    def compile_css_for_picker(css_form_dict):
        # Check css values
        for key in list(css_form_dict.keys()):
            if ';' in css_form_dict[key] or '}' in css_form_dict[key]:
                css_form_dict[key] = ''

        css_text = ""
        if 'projecttitlefont' in css_form_dict and css_form_dict['projecttitlefont'] != '':
            css_text += "/*projecttitlefont*/.project_title{font-family:%s;}\n" % (
                css_form_dict['projecttitlefont'])

        if 'projecttitlecolor' in css_form_dict and css_form_dict['projecttitlecolor'] != '':
            css_text += "/*projecttitlecolor*/.project_title{color:%s;}\n" % (
                css_form_dict['projecttitlecolor'])

        if 'barontop' in css_form_dict and css_form_dict['barontop'] != '':
            css_text += "/*barontop*/.pad h2.colored {background-color:%(bgcolor)s; background-image: none;}\n" % \
                        {'bgcolor': css_form_dict['barontop']}

        if 'titlebarbackground' in css_form_dict and css_form_dict['titlebarbackground'] != '':
            css_text += "/*titlebarbackground*/.pad h2.title{background-color:%(bgcolor)s; background-image: none;}\n" % \
                        {'bgcolor': css_form_dict['titlebarbackground']}

        if 'titlebarcolor' in css_form_dict and css_form_dict['titlebarcolor'] != '':
            css_text += "/*titlebarcolor*/.pad h2.title, .pad h2.title small a {color:%s;}\n" % (
                css_form_dict['titlebarcolor'])

        return css_text

    def migrate_css_for_picker(self):
        self.css = ""

    def get_anchored_tools(self):
        if not self.anchored_tools:
            return dict()
        try:
            anchored_tools = [at.strip()
                              for at in self.anchored_tools.split(',')]
            return OrderedDict((tool.split(':')[0].lower(), tool.split(':')[1]) for tool in anchored_tools)
        except Exception:
            log.warning("anchored_tools isn't valid", exc_info=True)
            return dict()

    def get_prohibited_tools(self):
        prohibited_tools = []
        if self.prohibited_tools:
            prohibited_tools = [tool.lower().strip() for tool in self.prohibited_tools.split(',')]
        return prohibited_tools
