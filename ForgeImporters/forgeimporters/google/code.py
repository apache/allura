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

import urllib2

import formencode as fe
from formencode import validators as fev

from pylons import tmpl_context as c
from pylons import app_globals as g
from tg import (
    expose,
    flash,
    redirect,
)
from tg.decorators import (
    with_trailing_slash,
    without_trailing_slash,
)

from allura.lib import validators as v
from allura.lib.decorators import require_post
from allura import model as M

from forgeimporters.base import (
    ToolImporter,
    ToolImportController,
)
from forgeimporters.google import GoogleCodeProjectExtractor
from forgeimporters.google import GoogleCodeProjectNameValidator


REPO_URLS = {
    'svn': 'http://{0}.googlecode.com/svn/',
    'git': 'https://code.google.com/p/{0}/',
    'hg': 'https://code.google.com/p/{0}/',
}


def get_repo_url(project_name, type_):
    return REPO_URLS[type_].format(project_name)


class GoogleRepoImportForm(fe.schema.Schema):
    gc_project_name = GoogleCodeProjectNameValidator()
    mount_point = fev.UnicodeString()
    mount_label = fev.UnicodeString()

    def __init__(self, *args):
        pass

    def _to_python(self, value, state):
        value = super(self.__class__, self)._to_python(value, state)

        gc_project_name = value['gc_project_name']
        mount_point = value['mount_point']
        try:
            repo_type = GoogleCodeProjectExtractor(
                gc_project_name).get_repo_type()
        except urllib2.HTTPError as e:
            if e.code == 404:
                msg = 'No such project'
            else:
                msg = str(e)
            msg = 'gc_project_name:' + msg
            raise fe.Invalid(msg, value, state)
        except Exception:
            raise
        tool_class = g.entry_points['tool'][repo_type]
        try:
            value['mount_point'] = v.MountPointValidator(
                tool_class).to_python(mount_point)
        except fe.Invalid as e:
            raise fe.Invalid('mount_point:' + str(e), value, state)
        return value


class GoogleRepoImportController(ToolImportController):
    import_form = GoogleRepoImportForm

    @with_trailing_slash
    @expose('jinja:forgeimporters.google:templates/code/index.html')
    def index(self, **kw):
        return dict(importer=self.importer,
                    target_app=self.target_app)

    @without_trailing_slash
    @expose()
    @require_post()
    def create(self, gc_project_name, mount_point, mount_label, **kw):
        if self.importer.enforce_limit(c.project):
            self.importer.post(
                project_name=gc_project_name,
                mount_point=mount_point,
                mount_label=mount_label)
            flash('Repo import has begun. Your new repo will be available '
                  'when the import is complete.')
        else:
            flash(
                'There are too many imports pending at this time.  Please wait and try again.', 'error')
        redirect(c.project.url() + 'admin/')


class GoogleRepoImporter(ToolImporter):
    target_app_ep_names = ('git', 'hg', 'svn')
    source = 'Google Code'
    controller = GoogleRepoImportController
    tool_label = 'Source Code'
    tool_description = 'Import your primary SVN, Git, or Hg repo from Google Code'

    def import_tool(self, project, user, project_name=None, mount_point=None,
                    mount_label=None, **kw):
        """ Import a Google Code repo into a new SVN, Git, or Hg Allura tool.

        """
        extractor = GoogleCodeProjectExtractor(project_name, 'source_browse')
        repo_type = extractor.get_repo_type()
        repo_url = get_repo_url(project_name, repo_type)
        app = project.install_app(
            repo_type,
            mount_point=mount_point or 'code',
            mount_label=mount_label or 'Code',
            init_from_url=repo_url,
            import_id={
                'source': self.source,
                'project_name': project_name,
            }
        )
        M.AuditLog.log(
            'import tool %s from %s on %s' % (
                app.config.options.mount_point,
                project_name, self.source,
            ), project=project, user=user, url=app.url)
        g.post_event('project_updated')
        return app
