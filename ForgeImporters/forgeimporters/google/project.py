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

from .. import base
from . import tasks


log = logging.getLogger(__name__)


class GoogleCodeProjectForm(base.ProjectImportForm):
    project_name = fev.Regex(r'^[a-z0-9][a-z0-9-]{,61}$',
            not_empty=True,
            messages={
                'invalid': 'Please use only letters, numbers, and dashes.',
            })


class GoogleCodeProjectImporter(base.ProjectImporter):
    """
    Project importer for Google Code.

    This imports project metadata, including summary, icon, and license,
    as well as providing the UI for importing individual tools during project
    import.
    """
    source = 'Google Code'
    process_validator = GoogleCodeProjectForm(source)
    index_template = 'jinja:forgeimporters.google:templates/project.html'

    def after_project_create(self, project, **kw):
        project.set_tool_data('google-code', project_name=project.name)
        tasks.import_project_info.post(project.name)

    @with_trailing_slash
    @expose(index_template)
    def index(self, **kw):
        return super(self.__class__, self).index(**kw)

    @require_post()
    @expose()
    @validate(process_validator, error_handler=index)
    def process(self, **kw):
        return super(self.__class__, self).process(**kw)

    @expose('json:')
    @validate(process_validator)
    def check_names(self, **kw):
        return super(self.__class__, self).check_names(**kw)
