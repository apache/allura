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

from tg import tmpl_context as c
from tg import app_globals as g
from tg import (
    expose,
    flash,
    redirect,
)
from tg.decorators import (
    with_trailing_slash,
    without_trailing_slash,
)

from allura.lib.decorators import require_post
from allura import model as M
from allura.lib import validators as v

from forgeimporters.base import (
    ToolImporter,
    ToolImportForm,
    ToolImportController,
)
from forgeimporters.github import (
    GitHubProjectExtractor,
    GitHubOAuthMixin,
    GitHubProjectNameValidator,
)


class GitHubRepoImportForm(ToolImportForm):
    gh_user_name = v.UnicodeString(not_empty=True)
    gh_project_name = GitHubProjectNameValidator()


class GitHubRepoImportController(ToolImportController, GitHubOAuthMixin):
    import_form = GitHubRepoImportForm

    @with_trailing_slash
    @expose('jinja:forgeimporters.github:templates/code/index.html')
    def index(self, **kw):
        self.oauth_begin()
        return dict(importer=self.importer,
                    target_app=self.target_app)

    @without_trailing_slash
    @expose()
    @require_post()
    def create(self, gh_project_name, gh_user_name, mount_point, mount_label, **kw):
        if self.importer.enforce_limit(c.project):
            self.importer.post(
                project_name=gh_project_name,
                user_name=gh_user_name,
                mount_point=mount_point,
                mount_label=mount_label)
            flash('Repo import has begun. Your new repo will be available '
                  'when the import is complete.')
        else:
            flash(
                'There are too many imports pending at this time.  Please wait and try again.', 'error')
        redirect(c.project.url() + 'admin/')


class GitHubRepoImporter(ToolImporter):
    target_app_ep_names = 'git'
    source = 'GitHub'
    controller = GitHubRepoImportController
    tool_label = 'Source Code'
    tool_description = 'Import your repo from GitHub'

    def import_tool(self, project, user, project_name=None, mount_point=None,
                    mount_label=None, user_name=None, **kw):
        """ Import a GitHub repo into a new Git Allura tool.

        """
        project_name = f"{user_name}/{project_name}"
        extractor = GitHubProjectExtractor(project_name, user=user)
        repo_url = extractor.get_repo_url()
        app = project.install_app(
            "Git",
            mount_point=mount_point or 'code',
            mount_label=mount_label or 'Code',
            init_from_url=repo_url,
            import_id={
                'source': self.source,
                'project_name': project_name,
            }
        )
        M.AuditLog.log(
            'import tool {} from {} on {}'.format(
                app.config.options.mount_point,
                project_name, self.source,
            ), project=project, user=user, url=app.url)
        g.post_event('project_updated')
        return app
