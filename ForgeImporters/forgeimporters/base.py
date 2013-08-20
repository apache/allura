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
import urllib2

from pkg_resources import iter_entry_points

from tg import expose, validate, flash, redirect, config
from tg.decorators import with_trailing_slash
from pylons import tmpl_context as c
from formencode import validators as fev, schema

from allura.lib.decorators import require_post
from allura.lib.decorators import task
from allura.lib.security import require_access
from allura.lib.plugin import ProjectRegistrationProvider
from allura.lib import helpers as h
from allura.lib import exceptions

from paste.deploy.converters import aslist

from ming.utils import LazyProperty
from allura.controllers import BaseController


log = logging.getLogger(__name__)


class ProjectImportForm(schema.Schema):
    def __init__(self, source):
        super(ProjectImportForm, self).__init__()
        provider = ProjectRegistrationProvider.get()
        self.add_field('tools', ToolsValidator(source))
        self.add_field('project_shortname', provider.shortname_validator)
        self.allow_extra_fields = True

    neighborhood = fev.PlainText(not_empty=True)
    project_name = fev.UnicodeString(not_empty=True, max=40)


@task(notifications_disabled=True)
def import_tool(importer_name, project_name=None, mount_point=None, mount_label=None, **kw):
    importer = ToolImporter.by_name(importer_name)
    importer.import_tool(c.project, c.user, project_name=project_name,
            mount_point=mount_point, mount_label=mount_label, **kw)


class ProjectExtractor(object):
    """Base class for project extractors.

    Subclasses should use :meth:`urlopen` to make HTTP requests, as it provides
    a custom User-Agent and automatically retries timed-out requests.

    """
    @staticmethod
    def urlopen(url, retries=3, codes=(408,), **kw):
        req = urllib2.Request(url, **kw)
        req.add_header('User-Agent', 'Allura Data Importer (http://sf.net/p/allura)')
        return h.urlopen(req, retries=retries, codes=codes)


class ProjectImporter(BaseController):
    """
    Base class for project importers.

    Subclasses are required to implement the :meth:`index()` and
    :meth:`process()` views described below.

    """
    source = None
    process_validator = None
    index_template = None

    def __init__(self, neighborhood, *a, **kw):
        self.neighborhood = neighborhood

    def _check_security(self):
        require_access(self.neighborhood, 'register')

    @LazyProperty
    def tool_importers(self):
        """
        List of all tool importers that import from the same source
        as this project importer.
        """
        tools = {}
        for ep in iter_entry_points('allura.importers'):
            epv = ep.load()
            if epv.source == self.source:
                tools[ep.name] = epv()
        return tools

    @with_trailing_slash
    @expose()
    def index(self, **kw):
        """
        Override and expose this view to present the project import form.

        The template used by this view should extend the base template in::

            jinja:forgeimporters:templates/project_base.html

        This will list the available tool importers.  Other project fields
        (e.g., project_name) should go in the project_fields block.
        """
        return {'importer': self, 'tg_template': self.index_template}

    @require_post()
    @expose()
    @validate(process_validator, error_handler=index)
    def process(self, **kw):
        """
        Override and expose this to handle a project import.

        This should at a minimum create the stub project with the appropriate
        tools installed and redirect to the new project, presumably with a
        message indicating that some data will not be available immediately.
        """
        try:
            c.project = self.neighborhood.register_project(kw['project_shortname'],
                    project_name=kw['project_name'])
        except exceptions.ProjectOverlimitError:
            flash("You have exceeded the maximum number of projects you are allowed to create", 'error')
            redirect('.')
        except exceptions.ProjectRatelimitError:
            flash("Project creation rate limit exceeded.  Please try again later.", 'error')
            redirect('.')
        except Exception:
            log.error('error registering project: %s', kw['project_shortname'], exc_info=True)
            flash('Internal Error. Please try again later.', 'error')
            redirect('.')

        self.after_project_create(c.project, **kw)
        for importer_name in kw['tools']:
            import_tool.post(importer_name, **kw)

        flash('Welcome to the %s Project System! '
              'Your project data will be imported and should show up here shortly.' % config['site_name'])
        redirect(c.project.script_name + 'admin/overview')

    @expose('json:')
    @validate(process_validator)
    def check_names(self, **kw):
        """
        Ajax form validation.

        """
        return c.form_errors

    def after_project_create(self, project, **kw):
        """
        Called after project is created.

        Useful for doing extra processing on the project before individual
        tool imports happen.

        :param project: The newly created project.
        :param \*\*kw: The keyword arguments that were posted to the controller
            method that created the project.

        """
        pass


class ToolImporter(object):
    """
    Base class for tool importers.

    Subclasses are required to implement :meth:`import_tool()` described
    below and define the following attributes:

    .. py:attribute:: target_app

       A reference or list of references to the tool(s) that this imports
       to.  E.g.::

            target_app = [forgegit.ForgeGitApp, forgehg.ForgeHgApp]

    .. py:attribute:: source

       A string indicating where this imports from.  This must match the
       `source` value of the :class:`ProjectImporter` for this importer to
       be discovered during full-project imports.  E.g.::

            source = 'Google Code'

    .. py:attribute:: controller

       The controller for this importer, to handle single tool imports.
    """
    target_app = None  # app or list of apps
    source = None  # string description of source, must match project importer
    controller = None

    @classmethod
    def by_name(self, name):
        """
        Return a ToolImporter subclass instance given its entry-point name.
        """
        for ep in iter_entry_points('allura.importers', name):
            return ep.load()()

    @classmethod
    def by_app(self, app):
        """
        Return a ToolImporter subclass instance given its target_app class.
        """
        importers = {}
        for ep in iter_entry_points('allura.importers'):
            importer = ep.load()
            if app in aslist(importer.target_app):
                importers[ep.name] = importer()
        return importers

    def import_tool(self, project, user, project_name=None,
            mount_point=None, mount_label=None, **kw):
        """
        Override this method to perform the tool import.

        :param project: the Allura project to import to
        :param project_name: the name of the remote project to import from
        :param mount_point: the mount point name, to override the default
        :param mount_label: the mount label name, to override the default
        """
        raise NotImplementedError

    @property
    def tool_label(self):
        """
        The label for this tool importer.  Defaults to the `tool_label` from
        the `target_app`.
        """
        return getattr(aslist(self.target_app)[0], 'tool_label', None)

    @property
    def tool_description(self):
        """
        The description for this tool importer.  Defaults to the `tool_description`
        from the `target_app`.
        """
        return getattr(aslist(self.target_app)[0], 'tool_description', None)

    def tool_icon(self, theme, size):
        return theme.app_icon_url(aslist(self.target_app)[0], size)


class ToolsValidator(fev.Set):
    """
    Validates the list of tool importers during a project import.

    This verifies that the tools selected are available and valid
    for this source.
    """
    def __init__(self, source, *a, **kw):
        super(ToolsValidator, self).__init__(*a, **kw)
        self.source = source

    def to_python(self, value, state=None):
        value = super(ToolsValidator, self).to_python(value, state)
        valid = []
        invalid = []
        for name in value:
            importer = ToolImporter.by_name(name)
            if importer is not None and importer.source == self.source:
                valid.append(name)
            else:
                invalid.append(name)
        if invalid:
            pl = 's' if len(invalid) > 1 else ''
            raise fev.Invalid('Invalid tool%s selected: %s' % (pl, ', '.join(invalid)), value, state)
        return valid
