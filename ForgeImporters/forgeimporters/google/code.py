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

import formencode as fe
from formencode import validators as fev

from pylons import tmpl_context as c
from pylons import app_globals as g
from tg import (
        expose,
        redirect,
        validate,
        )
from tg.decorators import (
        with_trailing_slash,
        without_trailing_slash,
        )

from allura.controllers import BaseController
from allura.lib.decorators import require_post

from forgeimporters.base import ToolImporter
from forgeimporters.google import GoogleCodeProjectExtractor

TARGET_APPS = []
try:
    from forgehg.hg_main import ForgeHgApp
    TARGET_APPS.append(ForgeHgApp)
except ImportError:
    pass
try:
    from forgegit.git_main import ForgeGitApp
    TARGET_APPS.append(ForgeGitApp)
except ImportError:
    pass
try:
    from forgesvn.svn_main import ForgeSVNApp
    TARGET_APPS.append(ForgeSVNApp)
except ImportError:
    pass

REPO_URLS = {
    'svn': 'http://{0}.googlecode.com/svn/',
    'git': 'https://code.google.com/p/{0}/',
    'hg': 'https://code.google.com/p/{0}/',
}
REPO_ENTRY_POINTS = {
    'svn': 'SVN',
    'git': 'Git',
    'hg': 'Hg',
}


def get_repo_url(project_name, type_):
    return REPO_URLS[type_].format(project_name)


class GoogleRepoImportSchema(fe.Schema):
    gc_project_name = fev.UnicodeString(not_empty=True)
    mount_point = fev.UnicodeString()
    mount_label = fev.UnicodeString()


class GoogleRepoImportController(BaseController):
    @with_trailing_slash
    @expose('jinja:forgeimporters.google:templates/code/index.html')
    def index(self, **kw):
        return {}

    @without_trailing_slash
    @expose()
    @require_post()
    @validate(GoogleRepoImportSchema(), error_handler=index)
    def create(self, gc_project_name, mount_point, mount_label, **kw):
        app = GoogleRepoImporter().import_tool(c.project, c.user,
                project_name=gc_project_name,
                mount_point=mount_point,
                mount_label=mount_label)
        redirect(app.url())


class GoogleRepoImporter(ToolImporter):
    target_app = TARGET_APPS
    source = 'Google Code'
    controller = GoogleRepoImportController
    tool_label = 'Source Code'
    tool_description = 'Import your SVN, Git, or Hg repo from Google Code'

    def import_tool(self, project, user, project_name=None, mount_point=None,
            mount_label=None, **kw):
        """ Import a Google Code repo into a new SVN, Git, or Hg Allura tool.

        """
        extractor = GoogleCodeProjectExtractor(project, project_name, 'source_browse')
        repo_type = extractor.get_repo_type()
        repo_url = get_repo_url(project_name, repo_type)
        app = project.install_app(
                REPO_ENTRY_POINTS[repo_type],
                mount_point=mount_point or 'code',
                mount_label=mount_label or 'Code',
                init_from_url=repo_url,
                )
        g.post_event('project_updated')
        return app
