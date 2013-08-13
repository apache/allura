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

import json
import os
import logging
import shutil

import tg
from pylons import app_globals as g

from allura import model as M
from allura.tasks import mail_tasks
from allura.lib.decorators import task
from allura.lib import helpers as h
from allura.model.repository import zipdir


log = logging.getLogger(__name__)


@task
def bulk_export(project_shortname, tools, username, neighborhood):
    neighborhood = M.Neighborhood.query.get(name=neighborhood)
    project = M.Project.query.get(shortname=project_shortname, neighborhood_id=neighborhood._id)
    if not project:
        log.error('Project %s not found' % project_shortname)
        return
    if project.bulk_export_status() == 'busy':
        log.info('Another export is running for project %s. Skipping.' % project_shortname)
        return
    not_exported_tools = []
    for tool in tools or []:
        app = project.app_instance(tool)
        if not app:
            log.info('Can not load app for %s mount point. Skipping.' % tool)
            not_exported_tools.append(tool)
            continue
        if not app.exportable:
            log.info('Tool %s is not exportable. Skipping.' % tool)
            not_exported_tools.append(tool)
            continue
        log.info('Exporting %s...' % tool)
        try:
            path = create_export_dir(project)
            with open(os.path.join(path, '%s.json' % tool), 'w') as f:
                with h.push_context(project._id, app_config_id=app.config._id):
                    app.bulk_export(f)
        except:
            log.error('Something went wrong during export of %s' % tool, exc_info=True)
            not_exported_tools.append(tool)
            continue

    try:
        path = create_export_dir(project)
        with open(os.path.join(path, 'project.json'), 'w') as f:
            json.dump(project, f, cls=tg.jsonify.GenericJSON, indent=2)
    except:
        log.error('Something went wrong during export of project metadata', exc_info=True)

    # If that fails, we need to let it fail
    # there won't be a valid zip file for the user to get.
    zip_and_cleanup(project)

    user = M.User.by_username(username)
    if not user:
        log.info('Can not find user %s. Skipping notification.' % username)
        return
    tmpl = g.jinja2_env.get_template('allura:templates/mail/bulk_export.html')
    instructions = tg.config.get('bulk_export_download_instructions', '')
    instructions = instructions.format(project=project.shortname)
    tmpl_context = {
        'instructions': instructions,
        'project': project,
        'tools': list(set(tools) - set(not_exported_tools)),
        'not_exported_tools': not_exported_tools,
    }
    email = {
        'fromaddr': unicode(user.email_address_header()),
        'reply_to': unicode(user.email_address_header()),
        'message_id': h.gen_message_id(),
        'destinations': [unicode(user._id)],
        'subject': u'Bulk export for project %s completed' % project_shortname,
        'text': tmpl.render(tmpl_context),
    }
    mail_tasks.sendmail.post(**email)


def create_export_dir(project):
    """Create temporary directory for export files"""
    zip_fn = project.bulk_export_filename()
    # Name temporary directory after project shortname,
    # thus zipdir() will use proper prefix inside the archive.
    tmp_dir_suffix = zip_fn.split('.')[0]
    path = os.path.join(project.bulk_export_path(), tmp_dir_suffix)
    if not os.path.exists(path):
        os.makedirs(path)
    return path


def zip_and_cleanup(project):
    """Zip exported data. Copy it to proper location. Remove temporary files."""
    path = project.bulk_export_path()
    zip_fn = project.bulk_export_filename()
    temp = os.path.join(path, zip_fn.split('.')[0])
    zip_path_temp = os.path.join(temp, zip_fn)
    zip_path = os.path.join(path, zip_fn)

    zipdir(temp, zip_path_temp)

    # cleanup
    shutil.move(zip_path_temp, zip_path)
    shutil.rmtree(temp)
