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

from pylons import tmpl_context as c
from pylons import app_globals as g
from formencode import validators as fev
from tg import (
        expose,
        flash,
        redirect,
        validate,
        )
from tg.decorators import (
        with_trailing_slash,
        without_trailing_slash,
        )

from allura.lib.decorators import require_post, task
from allura.controllers import BaseController

from forgegit.git_main import ForgeGitApp

from forgeimporters.base import (
        ToolImporter,
        ToolImportForm,
        ImportErrorHandler,
        )
from forgeimporters.github import GitHubProjectExtractor


@task(notifications_disabled=True)
def import_tool(**kw):
    importer = GitHubRepoImporter()
    with ImportErrorHandler(importer, kw.get('project_name')):
        importer.import_tool(c.project, c.user, **kw)


class GitHubRepoImportForm(ToolImportForm):
    gh_project_name = fev.UnicodeString(not_empty=True)
    gh_user_name = fev.UnicodeString(not_empty=True)


class GitHubRepoImportController(BaseController):
    def __init__(self):
        self.importer = GitHubRepoImporter()

    @property
    def target_app(self):
        return self.importer.target_app

    @with_trailing_slash
    @expose('jinja:forgeimporters.github:templates/code/index.html')
    def index(self, **kw):
        return dict(importer=self.importer,
                target_app=self.target_app)

    @without_trailing_slash
    @expose()
    @require_post()
    @validate(GitHubRepoImportForm(ForgeGitApp), error_handler=index)
    def create(self, gh_project_name, gh_user_name, mount_point, mount_label, **kw):
        import_tool.post(
                project_name=gh_project_name,
                user_name=gh_user_name,
                mount_point=mount_point,
                mount_label=mount_label)
        flash('Repo import has begun. Your new repo will be available '
                'when the import is complete.')
        redirect(c.project.url() + 'admin/')


class GitHubRepoImporter(ToolImporter):
    target_app = ForgeGitApp
    source = 'GitHub'
    controller = GitHubRepoImportController
    tool_label = 'Source Code'
    tool_description = 'Import your repo from GitHub'

    def import_tool(self, project, user, project_name=None, mount_point=None, mount_label=None, user_name=None, **kw):
        """ Import a GitHub repo into a new Git Allura tool.

        """
        project_name = "%s/%s" % (user_name, project_name)
        extractor = GitHubProjectExtractor(project_name)
        repo_url = extractor.get_repo_url()
        app = project.install_app(
            "Git",
            mount_point=mount_point or 'code',
            mount_label=mount_label or 'Code',
            init_from_url=repo_url,)
        g.post_event('project_updated')
        return app
