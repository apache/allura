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

from pylons import app_globals as g
from formencode import validators as fev

from allura.controllers import BaseController
from allura.lib import validators as v
from forgeimporters.base import ToolImporter
from forgeimporters.github import GitHubProjectExtractor

TARGET_APPS = []

try:
    from forgegit.git_main import ForgeGitApp
    TARGET_APPS.append(ForgeGitApp)
except ImportError:
    pass

@task(notifications_disabled=True)
def import_tool(**kw):
    GoogleRepoImporter().import_tool(c.project, c.user, **kw)


class GitHubRepoImportForm(fe.schema.Schema):
    gh_project_name = fev.UnicodeString(not_empty=True)
    mount_point = fev.UnicodeString()
    mount_label = fev.UnicodeString()

    def _to_python(self, value, state):
        value = super(self.__class__, self)._to_python(value, state)

        gh_project_name = value['gh_project_name']
        mount_point = value['mount_point']
        try:
            v.MountPointValidator('git').to_python(mount_point)
        except fe.Invalid as e:
            raise fe.Invalid('mount_point:' + str(e), value, state)
        return value


class GitHubRepoImportController(BaseController):
    def __init__(self):
        self.importer = GitHubRepoImporter()

    @property
    def target_app(self):
        return self.importer.target_app[0]

    @with_trailing_slash
    @expose('jinja:forgeimporters.google:templates/code/index.html')
    def index(self, **kw):
        return dict(importer=self.importer,
                target_app=self.target_app)

    @without_trailing_slash
    @expose()
    @require_post()
    @validate(GoogleRepoImportForm(), error_handler=index)
    def create(self, gc_project_name, mount_point, mount_label, **kw):
        import_tool.post(
                project_name=gc_project_name,
                mount_point=mount_point,
                mount_label=mount_label)
        flash('Repo import has begun. Your new repo will be available '
                'when the import is complete.')
        redirect(c.project.url() + 'admin/')



class GitHubRepoImporter(ToolImporter):
    target_app = TARGET_APPS
    source = 'GitHub'
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
