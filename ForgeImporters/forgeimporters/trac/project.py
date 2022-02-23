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

from tg import expose, validate
from tg.decorators import with_trailing_slash

from allura.lib.decorators import require_post
from allura.lib.validators import UserMapJsonFile

from forgeimporters import base
from forgeimporters.trac import TracURLValidator


log = logging.getLogger(__name__)


class TracProjectForm(base.ProjectImportForm):
    trac_url = TracURLValidator()
    user_map = UserMapJsonFile(as_string=True)


class TracProjectImporter(base.ProjectImporter):

    """
    Project importer for Trac.

    """
    source = 'Trac'
    process_validator = TracProjectForm(source)
    index_template = 'jinja:forgeimporters.trac:templates/project.html'

    def after_project_create(self, project, **kw):
        project.set_tool_data('trac', url=kw['trac_url'])

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
