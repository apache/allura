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

    @property
    def icon(self):
        return NeighborhoodFile.query.get(neighborhood_id=self._id)

