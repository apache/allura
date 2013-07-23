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

import formencode as fe
from formencode import validators as fev

from pylons import tmpl_context as c
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

from forgehg.hg_main import ForgeHgApp
from forgegit.git_main import ForgeGitApp
from forgesvn.svn_main import ForgeSVNApp

from forgeimporters.base import ToolImporter
from forgeimporters.google import GoogleCodeProjectExtractor


RE_REPO_TYPE = re.compile(r'(svn|hg|git)')
REPO_URLS = {
    'svn': 'http://{0}.googlecode.com/svn/trunk/',
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


def get_repo_type(extractor):
    repo_type = extractor.page.find(id="crumb_root")
    if not repo_type:
        raise Exception("Couldn't detect repo type: no #crumb_root in "
                "{0}".format(extractor.url))
    re_match = RE_REPO_TYPE.match(repo_type.text.lower())
    if re_match:
        return re_match.group(0)
    else:
        raise Exception("Unknown repo type: {0}".format(repo_type.text))


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
        c.project.set_tool_data('google-code', project_name=gc_project_name)
        app = GoogleRepoImporter.import_tool(c.project,
                mount_point=mount_point,
                mount_label=mount_label)
        redirect(app.url())


class GoogleRepoImporter(ToolImporter):
    target_app = (ForgeHgApp, ForgeGitApp, ForgeSVNApp)
    source = 'Google Code'
    controller = GoogleRepoImportController
    tool_label = 'Google Code Source Importer'
    tool_description = 'Import your SVN, Git, or Hg repo from Google Code'

    def import_tool(self, project=None, mount_point=None, mount_label=None):
        """ Import a Google Code repo into a new SVN, Git, or Hg Allura tool.

        """
        if not project:
            raise Exception("You must supply a project")
        if not project.get_tool_data('google-code', 'project_name'):
            raise Exception("Missing Google Code project name")
        extractor = GoogleCodeProjectExtractor(project, page='source_browse')
        repo_type = get_repo_type(extractor)
        repo_url = get_repo_url(project.get_tool_data('google-code',
            'project_name'), repo_type)
        return project.install_app(
                REPO_ENTRY_POINTS[repo_type],
                mount_point=mount_point or 'source',
                mount_label=mount_label or 'Source',
                init_from_url=repo_url,
                )
