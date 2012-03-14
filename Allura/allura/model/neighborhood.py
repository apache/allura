import re
import json
import logging

from ming import schema as S
from ming.orm import FieldProperty, RelationProperty, ForeignIdProperty
from ming.orm.declarative import MappedClass
from ming.utils import LazyProperty

import pylons
pylons.c = pylons.tmpl_context
pylons.g = pylons.app_globals
from pylons import request, c

from allura.lib import plugin

from .session import main_orm_session
from .filesystem import File

log = logging.getLogger(__name__)

class NeighborhoodFile(File):
    class __mongometa__:
        session = main_orm_session
    neighborhood_id=FieldProperty(S.ObjectId)

NEIGHBORHOOD_PROJECT_LIMITS = {
  "silver": 10,
  "gold": 20,
  "platinum": 30
}

re_gold_css_type = re.compile('^/\*(.+)\*/')
re_font_project_title = re.compile('font:(.+);\}')
re_color_project_title = re.compile('color:(.+);\}')
re_bgcolor_barontop = re.compile('background\-color:([^;}]+);')
re_bgcolor_titlebar = re.compile('background\-color:([^;}]+);')
re_color_titlebar = re.compile('color:([^;}]+);')

class Neighborhood(MappedClass):
    '''Provide a grouping of related projects.

    url_prefix - location of neighborhood (may include scheme and/or host)
    css - block of CSS text to add to all neighborhood pages
    '''
    class __mongometa__:
        session = main_orm_session
        name = 'neighborhood'

    _id = FieldProperty(S.ObjectId)
    name = FieldProperty(str)
    url_prefix = FieldProperty(str) # e.g. http://adobe.openforge.com/ or projects/
    shortname_prefix = FieldProperty(str, if_missing='')
    css = FieldProperty(str, if_missing='')
    homepage = FieldProperty(str, if_missing='')
    redirect = FieldProperty(str, if_missing='')
    projects = RelationProperty('Project')
    allow_browse = FieldProperty(bool, if_missing=True)
    site_specific_html = FieldProperty(str, if_missing='')
    project_template = FieldProperty(str, if_missing='')
    level = FieldProperty(str, if_missing='')
    allow_private = FieldProperty(bool, if_missing=True)

    def parent_security_context(self):
        return None

    @LazyProperty
    def neighborhood_project(self):
        from .project import Project
        return Project.query.get(
            neighborhood_id=self._id,
            shortname='--init--')

    @property
    def acl(self):
        return self.neighborhood_project.acl

    def url(self):
        url = self.url_prefix
        if url.startswith('//'):
            try:
                return request.scheme + ':' + url
            except TypeError: # pragma no cover
                return 'http:' + url
        else:
            return url

    def register_project(self, shortname, user=None, project_name=None, user_project=False, private_project=False, apps=None):
        '''Register a new project in the neighborhood.  The given user will
        become the project's superuser.  If no user is specified, c.user is used.
        '''
        provider = plugin.ProjectRegistrationProvider.get()
        if project_name is None:
            project_name = shortname
        return provider.register_project(
            self, shortname, project_name, user or getattr(c,'user',None), user_project, private_project, apps)

    def bind_controller(self, controller):
        from allura.controllers.project import NeighborhoodController
        controller_attr = self.url_prefix[1:-1]
        setattr(controller, controller_attr, NeighborhoodController(
                self.name, self.shortname_prefix))

    def get_custom_css(self):
        if self.level in ["gold", "platinum"]:
            return self.css
        return ""

    def should_show_icon(self):
        return self.level in ('silver', 'gold', 'platinum')

    @property
    def icon(self):
        return NeighborhoodFile.query.get(neighborhood_id=self._id)

    def get_project_template(self):
        if self.project_template:
            return json.loads(self.project_template)
        return {}

    def get_max_projects(self):
        if self.level is not None and self.level != '':
            if self.level in NEIGHBORHOOD_PROJECT_LIMITS:
                return NEIGHBORHOOD_PROJECT_LIMITS[self.level]
            else:
                return 0
        return None

    def get_css_for_gold_level(self):
        projecttitlefont = {'label': 'Project title, font', 'name': 'projecttitlefont', 'value':'', 'type': 'font'}
        projecttitlecolor = {'label': 'Project title, color', 'name': 'projecttitlecolor', 'value':'', 'type': 'color'}
        barontop = {'label': 'Bar on top', 'name': 'barontop', 'value': '', 'type': 'color'}
        titlebarbackground = {'label': 'Title bar, background', 'name': 'titlebarbackground', 'value': '', 'type': 'color'}
        titlebarcolor = {'label': 'Title bar, foreground', 'name': 'titlebarcolor', 'value': '', 'type': 'color'}

        if self.css is not None:
            for css_line in self.css.split('\n'):
                m = re_gold_css_type.search(css_line)
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
    def compile_css_for_gold_level(css_form_dict):
        # Check css values
        for key in css_form_dict.keys():
            if ';' in css_form_dict[key] or '}' in css_form_dict[key]:
                css_form_dict[key] = ''

        css_text = ""
        if 'projecttitlefont' in css_form_dict and css_form_dict['projecttitlefont'] != '':
           css_text += "/*projecttitlefont*/.project_title{font:%s;}\n" % (css_form_dict['projecttitlefont'])

        if 'projecttitlecolor' in css_form_dict and css_form_dict['projecttitlecolor'] != '':
           css_text += "/*projecttitlecolor*/.project_title{color:%s;}\n" % (css_form_dict['projecttitlecolor'])

        if 'barontop' in css_form_dict and css_form_dict['barontop'] != '':
           css_text += "/*barontop*/.pad h2.colored {background-color:%(bgcolor)s; background-image: none;}\n" % \
                       {'bgcolor': css_form_dict['barontop']}

        if 'titlebarbackground' in css_form_dict and css_form_dict['titlebarbackground'] != '':
           css_text += "/*titlebarbackground*/.pad h2.title{background-color:%(bgcolor)s; background-image: none;}\n" % \
                       {'bgcolor': css_form_dict['titlebarbackground']}

        if 'titlebarcolor' in css_form_dict and css_form_dict['titlebarcolor'] != '':
           css_text += "/*titlebarcolor*/.pad h2.title{color:%s;}\n" % (css_form_dict['titlebarcolor'])

        return css_text

    def migrate_css_for_gold_level(self):
        self.css = ""
