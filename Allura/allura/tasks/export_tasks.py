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

import os
import logging

from allura import model as M
from allura.lib.decorators import task


log = logging.getLogger(__name__)


@task
def bulk_export(project_shortname, tools):
    project = M.Project.query.get(shortname=project_shortname)
    if not project:
        log.error('Project %s not found' % project_shortname)
        return
    for tool in tools or []:
        app = project.app_instance(tool)
        if not app:
            log.info('Can not load app for %s mount point. Skipping.' % tool)
            continue
        if not app.exportable:
            log.info('Tool %s is not exportable. Skipping.' % tool)
            continue
        log.info('Exporting %s...' % tool)
        try:
            path = create_export_dir(project)
            with open(os.path.join(path, '%s.json' % tool), 'w') as f:
                app.bulk_export(f)
        except:
            log.error('Something went wrong during export of %s' % tool, exc_info=True)
            continue

    try:
        cleanup()
    except:
        log.error('Error on cleanup.', exc_info=True)


def create_export_dir(project):
    """Create temporary directory for export files"""
    path = os.path.join(project.bulk_export_path(), 'tmp')
    if not os.path.exists(path):
        os.makedirs(path)
    return path


def cleanup():
    """Copy zip with export data to proper location. Remove temporary files."""
    pass
