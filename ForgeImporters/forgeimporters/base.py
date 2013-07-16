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

from pkg_resources import iter_entry_points

from tg import expose
from formencode import validators as fev

from ming.utils import LazyProperty
from allura.controllers import BaseController


class ProjectImporterDispatcher(BaseController):
    @expose()
    def _lookup(self, source, *rest):
        for ep in iter_entry_points('allura.project_importers', source):
            return ep.load()(), rest


class ProjectImporter(BaseController):
    source = None

    @LazyProperty
    def tool_importers(self):
        tools = {}
        for ep in iter_entry_points('allura.importers'):
            epv = ep.load()
            if epv.source == self.source:
                tools[ep.name] = epv()
        return tools

    def index(self, **kw):
        """
        Override and expose this view to present the project import form.

        The template used by this view should extend the base template in:

            jinja:forgeimporters:templates/project_base.html

        This will list the available tool importers.  Other project fields
        (e.g., project_name) should go in the project_fields block.
        """
        raise NotImplemented

    def process(self, tools=None, **kw):
        """
        Override and expose this to handle a project import.

        This should at a minimum create the stub project with the appropriate
        tools installed and redirect to the new project, presumably with a
        message indicating that some data will not be available immediately.
        """
        raise NotImplemented


class ToolImporter(object):
    target_app = None
    source = None
    controller = None

    def import_tool(self, project, mount_point):
        """
        Override this method to perform the tool import.
        """
        raise NotImplementedError

    @property
    def tool_label(self):
        return getattr(self.target_app, 'tool_label', None)

    @property
    def tool_description(self):
        return getattr(self.target_app, 'tool_description', None)


class ToolsValidator(fev.Set):
    def __init__(self, source, *a, **kw):
        super(ToolsValidator, self).__init__(*a, **kw)
        self.source = source

    def to_python(self, value, state=None):
        value = super(ToolsValidator, self).to_python(value, state)
        valid = []
        invalid = []
        for i, v in enumerate(value):
            try:
                ep = iter_entry_points('allura.importers', v).next().load()
            except StopIteration:
                ep = None
            if getattr(ep, 'source', None) != self.source:
                invalid.append(v)
            else:
                valid.append(ep())
        if invalid:
            pl = 's' if len(invalid) > 1 else ''
            raise fev.Invalid('Invalid tool%s selected: %s' % (pl, ', '.join(invalid)), value, state)
        return valid
