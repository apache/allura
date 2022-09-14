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

import os
import errno
import logging
from io import BytesIO

import six.moves.urllib.request
import six.moves.urllib.parse
import six.moves.urllib.error
from collections import defaultdict
import traceback
from six.moves.urllib.parse import urlparse
from six.moves.urllib.parse import unquote
from datetime import datetime
import six

from bs4 import BeautifulSoup
from tg import expose, validate, flash, redirect, config
from tg.decorators import with_trailing_slash
from tg import app_globals as g
from tg import tmpl_context as c
from formencode import validators as fev, schema
from webob import exc

from allura.lib.decorators import require_post
from allura.lib.decorators import task
from allura.lib.security import require_access
from allura.lib.plugin import ProjectRegistrationProvider, AdminExtension
from allura.lib.utils import guess_mime_type
from allura.lib import helpers as h
from allura.lib import exceptions
from allura.lib import validators as v
from allura.app import SitemapEntry
from allura import model as M

from paste.deploy.converters import aslist

from ming.utils import LazyProperty
from allura.controllers import BaseController


log = logging.getLogger(__name__)


class ProjectImportForm(schema.Schema):

    def __init__(self, source):
        super().__init__()
        provider = ProjectRegistrationProvider.get()
        self.add_field('tools', ToolsValidator(source))
        self.add_field('project_shortname', provider.shortname_validator)
        self.allow_extra_fields = True

    neighborhood = fev.NotEmpty()
    project_name = v.UnicodeString(not_empty=True, max=40)


class ToolImportForm(schema.Schema):

    def __init__(self, tool_class):
        super().__init__()
        self.add_field('mount_point', v.MountPointValidator(tool_class))
    mount_label = v.UnicodeString()


class ImportErrorHandler:

    def __init__(self, importer, project_name, project):
        self.importer = importer
        self.project_name = project_name
        self.project = project

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self.importer, 'clear_pending'):
            self.importer.clear_pending(self.project)
        if exc_type:
            g.post_event('import_tool_task_failed',
                         error=str(exc_val),
                         traceback=traceback.format_exc(),
                         importer_source=self.importer.source,
                         importer_tool_label=self.importer.tool_label,
                         project_name=self.project_name,
                         )

    def success(self, app):
        with h.push_config(c, project=self.project, app=app):
            g.post_event('import_tool_task_succeeded',
                         self.importer.source,
                         self.importer.tool_label,
                         )


def object_from_path(path):
    """Given a dotted path, import and return the object at that path.

    """
    module_name, obj_name = path.rsplit('.', 1)
    module = __import__(module_name, fromlist=[obj_name])
    return getattr(module, obj_name)


@task(notifications_disabled=True)
def import_tool(importer_path, project_name=None,
                mount_point=None, mount_label=None, **kw):
    importer = object_from_path(importer_path)()
    with ImportErrorHandler(importer, project_name, c.project) as handler,\
            M.session.substitute_extensions(M.artifact_orm_session,
                                            [M.session.BatchIndexer]):
        try:
            M.artifact_orm_session._get().skip_last_updated = True
            app = importer.import_tool(
                c.project, c.user, project_name=project_name,
                mount_point=mount_point, mount_label=mount_label, **kw)
            # manually update project's last_updated field at the end of the
            # import instead of it being updated automatically by each artifact
            # since long-running task can cause stale project data to be saved
            M.Project.query.update(
                {'_id': c.project._id},
                {'$set': {'last_updated': datetime.utcnow()}})
        finally:
            M.artifact_orm_session._get().skip_last_updated = False
        M.artifact_orm_session.flush()
        M.session.BatchIndexer.flush()
        if app:
            with h.notifications_disabled(c.project, disabled=False):
                g.director.create_activity(c.user, "imported", app.config,
                                           related_nodes=[c.project], tags=['import'])
            handler.success(app)


class ProjectExtractor:

    """Base class for project extractors.

    Subclasses should use :meth:`urlopen` to make HTTP requests, as it provides
    a custom User-Agent and automatically retries timed-out requests.

    """

    PAGE_MAP = {}

    def __init__(self, project_name, page_name=None, **kw):
        self.project_name = project_name
        self._page_cache = {}
        self.url = None
        self.page = None
        if page_name:
            self.get_page(page_name, **kw)

    @staticmethod
    def urlopen(url, retries=3, codes=(408, 500, 502, 503, 504), timeout=120, unredirected_hdrs=None, **kw):
        req = six.moves.urllib.request.Request(url, **kw)
        if unredirected_hdrs:
            for key, val in unredirected_hdrs.items():
                req.add_unredirected_header(key, val)
        req.add_header('User-Agent', 'Allura Data Importer (https://allura.apache.org/)')
        return h.urlopen(req, retries=retries, codes=codes, timeout=timeout)

    def get_page(self, page_name_or_url, parser=None, **kw):
        """Return a Beautiful soup object for the given page name or url.

        If a page name is provided, the associated url is looked up in
        :attr:`PAGE_MAP`.

        If provided, the class or callable passed in :param:`parser` will be
        used to transform the result of the `urlopen` before returning it.
        Otherwise, the class's :meth:`parse_page` will be used.

        Results are cached so that subsequent calls for the same page name or
        url will return the cached result rather than making another HTTP
        request.

        """
        if page_name_or_url in self.PAGE_MAP:
            self.url = self.get_page_url(page_name_or_url, **kw)
        else:
            self.url = page_name_or_url
        if self.url in self._page_cache:
            self.page = self._page_cache[self.url]
        else:
            if parser is None:
                parser = self.parse_page
            self.page = self._page_cache[self.url] = \
                parser(self.urlopen(self.url))
        return self.page

    def get_page_url(self, page_name, **kw):
        """Return the url associated with ``page_name``.

        Raises KeyError if ``page_name`` is not in :attr:`PAGE_MAP`.

        """
        return self.PAGE_MAP[page_name].format(
            project_name=six.moves.urllib.parse.quote(self.project_name), **kw)

    def parse_page(self, page):
        """Transforms the result of a `urlopen` call before returning it from
        :meth:`get_page`.

        The default implementation create a :class:`BeautifulSoup` object from
        the html.

        Subclasses can override to change the behavior or handle other types
        of content (like JSON).  The parser can also be overridden via the
        `parser` parameter to :meth:`get_page`

        :param page: A file-like object return from :meth:`urlopen`

        """
        return BeautifulSoup(page, convertEntities=BeautifulSoup.HTML_ENTITIES)


class ProjectImporter(BaseController):

    """
    Base class for project importers.

    Subclasses are required to implement the :meth:`index()` and
    :meth:`process()` views described below.

    """
    source = None
    tool_label = 'Project Info'
    process_validator = None
    index_template = None

    def __init__(self, neighborhood, *a, **kw):
        self.neighborhood = neighborhood

    def _check_security(self):
        with h.login_overlay(exceptions=['process']):
            require_access(self.neighborhood, 'register')

    @LazyProperty
    def tool_importers(self):
        """
        List of all tool importers that import from the same source
        as this project importer.
        """
        tools = {}
        for ep in h.iter_entry_points('allura.importers'):
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
            with h.push_config(config, **{'project.verify_phone': 'false'}):
                c.project = self.neighborhood.register_project(
                    kw['project_shortname'],
                    project_name=kw['project_name'])
        except exceptions.ProjectOverlimitError:
            flash("You have exceeded the maximum number of projects you are allowed to create", 'error')
            redirect('.')
        except exceptions.ProjectRatelimitError:
            flash("Project creation rate limit exceeded.  Please try again later.", 'error')
            redirect('.')
        except Exception:
            log.error('error registering project: %s',
                      kw['project_shortname'], exc_info=True)
            flash('Internal Error. Please try again later.', 'error')
            redirect('.')

        self.after_project_create(c.project, **kw)
        tools = aslist(kw.get('tools'))

        for importer_name in tools:
            ToolImporter.by_name(importer_name).post(**kw)
        M.AuditLog.log('import project from %s' % self.source)

        flash('Welcome to your new project on %s! '
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
        :param kw: The keyword arguments that were posted to the controller
            method that created the project.

        """
        pass


class ToolImportControllerMeta(type):
    def __call__(cls, importer, *args, **kw):
        """ Decorate the `create` post handler with a validator that references
        the appropriate App for this controller's importer.

        """
        if hasattr(cls, 'create') and getattr(cls.create.decoration, 'validation', None) is None:
            index_meth = getattr(cls.index, '__func__', cls.index)
            cls.create = validate(cls.import_form(aslist(importer.target_app)[0]),
                                  error_handler=index_meth)(cls.create)
        return type.__call__(cls, importer, *args, **kw)


class ToolImportController(BaseController, metaclass=ToolImportControllerMeta):
    """ Base class for ToolImporter controllers.

    """

    def __init__(self, importer):
        """
        :param importer: :class:`ToolImporter` instance to which this
            controller belongs.

        """
        self.importer = importer

    @property
    def target_app(self):
        return aslist(self.importer.target_app)[0]


class ToolImporterMeta(type):
    def __init__(cls, name, bases, attrs):
        if not (hasattr(cls, 'target_app_ep_names')
                or hasattr(cls, 'target_app')):
            raise AttributeError(f"{name} must define either `target_app` or `target_app_ep_names`")
        return type.__init__(cls, name, bases, attrs)

    def __call__(cls, *args, **kw):
        """ Right before the first instance of cls is created, get
        the list of target_app classes from ep names. Can't do this
        at cls create/init time b/c g.entry_points is not guaranteed
        to be loaded at that point.

        """
        if not getattr(cls, 'target_app', None):
            cls.target_app = [g.entry_points['tool'][ep_name]
                              for ep_name in aslist(cls.target_app_ep_names)
                              if ep_name in g.entry_points['tool']]
        return type.__call__(cls, *args, **kw)


class ToolImporter(metaclass=ToolImporterMeta):

    """
    Base class for tool importers.

    Subclasses are required to implement :meth:`import_tool()` described
    below and define the following attributes:

    .. py:attribute:: target_app_ep_names

       A string or list of strings which are entry point names of the
       tool(s) to which this class imports. E.g.::

            target_app_ep_names = ['git', 'hg']

    .. py:attribute:: target_app

       A reference or list of references to the tool(s) that this imports
       to.  This attribute is not required if `target_app_ep_names` is
       defined (which is preferable). E.g.::

            target_app = [forgegit.ForgeGitApp, forgehg.ForgeHgApp]

    .. py:attribute:: source

       A string indicating where this imports from.  This must match the
       `source` value of the :class:`ProjectImporter` for this importer to
       be discovered during full-project imports.  E.g.::

            source = 'GitHub'

    .. py:attribute:: controller

       The controller for this importer, to handle single tool imports.

    """

    target_app = None  # app or list of apps
    source = None  # string description of source, must match project importer
    controller = None

    @staticmethod
    def by_name(name):
        """
        Return a ToolImporter subclass instance given its entry-point name.
        """
        for ep in h.iter_entry_points('allura.importers', name):
            return ep.load()()

    @staticmethod
    def by_app(app):
        """
        Return a ToolImporter subclass instance given its target_app class.
        """
        importers = {}
        for ep in h.iter_entry_points('allura.importers'):
            importer = ep.load()
            if app in aslist(importer.target_app):
                importers[ep.name] = importer()
        return importers

    @property
    def classname(self):
        return self.__class__.__name__

    def enforce_limit(self, project):
        """
        Enforce rate limiting of tool imports on a given project.

        Returns False if limit is met / exceeded.  Otherwise, increments the
        count of pending / in-progress imports and returns True.
        """
        limit = config.get('tool_import.rate_limit', 1)
        pending_key = 'tool_data.%s.pending' % self.classname
        modified_project = M.Project.query.find_and_modify(
            query={
                '_id': project._id,
                '$or': [
                    {pending_key: None},
                    {pending_key: {'$lt': limit}},
                ],
            },
            update={'$inc': {pending_key: 1}},
            new=True,
        )
        return modified_project is not None

    def clear_pending(self, project):
        """
        Decrement the pending counter for this importer on the given project,
        to indicate that an import is complete.
        """
        pending_key = 'tool_data.%s.pending' % self.classname
        M.Project.query.find_and_modify(
            query={'_id': project._id},
            update={'$inc': {pending_key: -1}},
            new=True,
        )

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
    def tool_option(self):
        """
        The option for this tool importer. Defaults to the `tool_option` from
        the `target_app`.
        """
        return getattr(aslist(self.target_app)[0], 'tool_option', dict())

    @property
    def tool_description(self):
        """
        The description for this tool importer.  Defaults to the `tool_description`
        from the `target_app`.
        """
        return getattr(aslist(self.target_app)[0], 'tool_description', None)

    def tool_icon(self, theme, size):
        return theme.app_icon_url(aslist(self.target_app)[0], size)

    def post(self, **kw):
        """Post a task that will call ``import_tool()`` on this instance.

        """
        klass = self.__class__
        importer_path = f'{klass.__module__}.{klass.__name__}'
        import_tool.post(importer_path, **kw)


class ToolsValidator(fev.Set):

    """
    Validates the list of tool importers during a project import.

    This verifies that the tools selected are available and valid
    for this source.
    """

    def __init__(self, source, *a, **kw):
        super().__init__(*a, **kw)
        self.source = source

    def to_python(self, value, state=None):
        value = super().to_python(value, state)
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
            raise fev.Invalid('Invalid tool%s selected: %s' %
                              (pl, ', '.join(invalid)), value, state)
        return valid


class ProjectToolsImportController:

    '''List all importers available'''

    @with_trailing_slash
    @expose('jinja:forgeimporters:templates/list_all.html')
    def index(self, *a, **kw):
        importer_matrix = defaultdict(dict)
        tools_with_importers = set()
        hidden = set(aslist(config.get('hidden_importers'), sep=','))
        visible = lambda ep: ep.name not in hidden
        for ep in filter(visible, h.iter_entry_points('allura.importers')):
            # must instantiate to ensure importer.target_app is populated
            # (see ToolImporterMeta.__call__)
            importer = ep.load()()
            for tool in aslist(importer.target_app):
                tools_with_importers.add(tool.tool_label)
                importer_matrix[importer.source][tool.tool_label] = ep.name
        return {
            'importer_matrix': importer_matrix,
            'tools': tools_with_importers,
        }

    @expose()
    def _lookup(self, name, *remainder):
        importer = ToolImporter.by_name(name)
        if importer:
            return importer.controller(importer), remainder
        else:
            raise exc.HTTPNotFound


class ImportAdminExtension(AdminExtension):

    '''Add import link to project admin sidebar'''

    project_admin_controllers = {'import': ProjectToolsImportController}

    def update_project_sidebar_menu(self, sidebar_links):
        base_url = c.project.url() + 'admin/ext/'
        link = SitemapEntry('Import', base_url + 'import/')
        sidebar_links.append(link)


def bytesio_parser(page):
    return {
        'content-type': page.info()['content-type'],
        'data': BytesIO(page.read()),
    }


class File:

    def __init__(self, url, filename=None):
        extractor = ProjectExtractor(None, url, parser=bytesio_parser)
        self.url = url
        self.filename = filename or unquote(os.path.basename(urlparse(url).path))
        # try to get the mime-type from the filename first, because
        # some files (e.g., attachements) may have the Content-Type header
        # forced to encourage the UA to download / save the file
        self.type = guess_mime_type(self.filename)
        if self.type == 'application/octet-stream':
            # however, if that fails, fall back to the given mime-type,
            # as some files (e.g., project icons) might have no file
            # extension but return a valid Content-Type header
            self.type = extractor.page['content-type']
        self.file = extractor.page['data']


def get_importer_upload_path(project):
    shortname = project.shortname
    if project.is_nbhd_project:
        shortname = project.url().strip('/')
    elif project.is_user_project:
        shortname = project.shortname.split('/')[1]
    elif not project.is_root:
        shortname = project.shortname.split('/')[0]
    upload_path = config['importer_upload_path'].format(
        nbhd=project.neighborhood.url_prefix.strip('/'),
        project=shortname,
        c=c,
    )
    return upload_path


def save_importer_upload(project, filename, data):
    dest_path = get_importer_upload_path(project)
    dest_file = os.path.join(dest_path, filename)
    try:
        os.makedirs(dest_path)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
    with open(dest_file, 'w', encoding='utf-8') as fp:
        fp.write(data)
    return dest_file
