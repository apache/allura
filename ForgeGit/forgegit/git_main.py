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

# Non-stdlib imports
from tg import tmpl_context as c

from ming.utils import LazyProperty
from ming.orm.ormsession import ThreadLocalORMSession
from timermiddleware import Timer
import git

# Pyforge-specific imports
import allura.tasks.repo_tasks
from allura.controllers.repository import RepoRootController, RefsController, CommitsController
from allura.controllers.repository import MergeRequestsController, RepoRestController
from allura.lib.repository import RepositoryApp
from allura.app import SitemapEntry

# Local imports
from . import model as GM
from . import version
from .controllers import BranchBrowser

log = logging.getLogger(__name__)


class ForgeGitApp(RepositoryApp):

    '''This is the Git app for PyForge'''
    __version__ = version.__version__
    tool_label = 'Git'
    tool_description = """
        Git is a popular distributed version control system with broad functionality.
        It is known for its speed, flexibility, and data integrity.
    """
    ordinal = 2
    forkable = True

    def __init__(self, project, config):
        super().__init__(project, config)
        self.root = RepoRootController()
        self.api_root = RepoRestController()
        self.root.ref = RefsController(BranchBrowser)
        self.root.ci = CommitsController()
        setattr(self.root, 'merge-requests', MergeRequestsController())

    @LazyProperty
    def repo(self):
        return GM.Repository.query.get(app_config_id=self.config._id)

    @property
    def default_branch_name(self):
        return self.repo.get_default_branch('master')

    def admin_menu(self):
        links = []
        links.append(SitemapEntry(
            'Set default branch',
            c.project.url() + 'admin/' + self.config.options.mount_point +
            '/' + 'set_default_branch_name',
            className='admin_modal'))
        links += super().admin_menu()
        return links

    def install(self, project):
        '''Create repo object for this tool'''
        super().install(project)
        repo = GM.Repository(
            name=self.config.options.mount_point + '.git',
            tool='git',
            status='initializing',
            fs_path=self.config.options.get('fs_path'))
        ThreadLocalORMSession.flush_all()
        cloned_from_project_id = self.config.options.get('cloned_from_project_id')
        cloned_from_repo_id = self.config.options.get('cloned_from_repo_id')
        init_from_url = self.config.options.get('init_from_url')
        init_from_path = self.config.options.get('init_from_path')
        if cloned_from_project_id is not None:
            cloned_from = GM.Repository.query.get(_id=cloned_from_repo_id)
            repo.default_branch_name = cloned_from.default_branch_name
            repo.additional_viewable_extensions = cloned_from.additional_viewable_extensions
            allura.tasks.repo_tasks.clone.post(
                cloned_from_path=cloned_from.full_fs_path,
                cloned_from_name=cloned_from.app.config.script_name(),
                cloned_from_url=cloned_from.full_fs_path)
        elif init_from_url or init_from_path:
            allura.tasks.repo_tasks.clone.post(
                cloned_from_path=init_from_path,
                cloned_from_name=None,
                cloned_from_url=init_from_url)
        else:
            allura.tasks.repo_tasks.init.post()


def git_timers():
    return [
        Timer('git_lib.{method_name}', git.Repo,
              'rev_parse', 'iter_commits', 'commit'),
        Timer('git_lib.{method_name}', GM.git_repo.GitLibCmdWrapper, 'log'),
    ]


def forgegit_timers():
    return Timer('git_tool.{method_name}', GM.git_repo.GitImplementation, '*')
