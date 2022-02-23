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

from ming.orm import ThreadLocalORMSession

from allura.lib.decorators import task

from forgeimporters.base import ImportErrorHandler
from forgeimporters.github import GitHubProjectExtractor


@task
def import_project_info(project_name):
    from forgeimporters.github.project import GitHubProjectImporter
    importer = GitHubProjectImporter(None)
    with ImportErrorHandler(importer, project_name, c.project) as handler:
        extractor = GitHubProjectExtractor(project_name, user=c.user)
        c.project.summary = extractor.get_summary()
        c.project.external_homepage = extractor.get_homepage()
        ThreadLocalORMSession.flush_all()
        g.post_event('project_updated')
