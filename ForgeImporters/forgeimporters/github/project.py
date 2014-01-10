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

from formencode import validators as fev

from tg import expose, validate
from tg.decorators import with_trailing_slash

from allura.lib.decorators import require_post
from allura.lib import helpers as h

from .. import base
from . import tasks
from . import GitHubOAuthMixin


log = logging.getLogger(__name__)


class GitHubProjectForm(base.ProjectImportForm):
    project_name = fev.Regex(r'^[a-zA-Z0-9-_.]+$',
                             not_empty=True,
                             messages={
                                 'invalid': 'Valid symbols are: letters, numbers, dashes, underscores and periods',
                             })


class GitHubProjectImporter(base.ProjectImporter, GitHubOAuthMixin):

    source = 'GitHub'
    index_template = 'jinja:forgeimporters.github:templates/project.html'
    process_validator = GitHubProjectForm(source)

    def after_project_create(self, project, **kw):
        project.set_tool_data('github', project_name=project.name)
        project_name = '%s/%s' % (kw['user_name'], kw['project_name'])
        tasks.import_project_info.post(project_name)

    @with_trailing_slash
    @expose(index_template)
    def index(self, **kw):
        self.oauth_begin()
        return super(self.__class__, self).index(**kw)

    @require_post()
    @expose()
    @validate(process_validator)
    def process(self, **kw):
        if not type(kw['tools']) == list:
            kw['tools'] = [kw['tools']]
        return super(self.__class__, self).process(**kw)

    @expose('json:')
    @validate(process_validator)
    def check_names(self, **kw):
        return super(self.__class__, self).check_names(**kw)
