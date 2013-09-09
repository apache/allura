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
import os.path
import logging
import shutil
from tempfile import mkstemp

import tg
from pylons import app_globals as g, tmpl_context as c

from allura import model as M
from allura.tasks import mail_tasks
from allura.lib.decorators import task
from allura.lib import helpers as h
from allura.model.repository import zipdir


log = logging.getLogger(__name__)


@task
def bulk_export(tools):
    '''
    Export the current project data.  Send notification to current user

    :param list tools: list of mount_points to export
    '''
    # it's very handy to use c.* within a @task,
    # but let's be explicit and keep it separate from the main code
    return _bulk_export(c.project, tools, c.user)


def _bulk_export(project, tools, user):
    export_filename = project.bulk_export_filename()
    export_path = create_export_dir(project, export_filename)
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
            json_file = os.path.join(export_path, '%s.json' % tool)
            with open(json_file, 'w') as f:
                app.bulk_export(f)
        except:
            log.error('Something went wrong during export of %s' % tool, exc_info=True)
            not_exported_tools.append(tool)
            continue

    if tools and len(not_exported_tools) < len(tools):
        # If that fails, we need to let it fail
        # there won't be a valid zip file for the user to get.
        zip_and_cleanup(export_path, export_filename)
    else:
        log.error('Nothing to export')
        return None

    if not user:
        log.info('No user. Skipping notification.')
        return
    tmpl = g.jinja2_env.get_template('allura:templates/mail/bulk_export.html')
    instructions = tg.config.get('bulk_export_download_instructions', '')
    instructions = instructions.format(project=project.shortname, filename=export_filename, c=c)
    tmpl_context = {
        'instructions': instructions,
        'project': project,
        'tools': list(set(tools) - set(not_exported_tools)),
        'not_exported_tools': not_exported_tools,
    }
    email = {
        'fromaddr': unicode(tg.config['forgemail.return_path']),
        'reply_to': unicode(user.email_address_header()),
        'message_id': h.gen_message_id(),
        'destinations': [unicode(user._id)],
        'subject': u'Bulk export for project %s completed' % project.shortname,
        'text': tmpl.render(tmpl_context),
    }
    mail_tasks.sendmail.post(**email)


def create_export_dir(project, export_filename):
    """Create temporary directory for export files"""
    # Name temporary directory after project shortname,
    # thus zipdir() will use proper prefix inside the archive.
    tmp_dir_suffix = os.path.splitext(export_filename)[0]
    path = os.path.join(project.bulk_export_path(), tmp_dir_suffix)
    if not os.path.exists(path):
        os.makedirs(path)
    return path


def zip_and_cleanup(export_path, export_filename):
    """
    Zip exported data for a given path and filename.
    Copy it to proper location. Remove temporary files.
    """
    zipdir(export_path, os.path.join(os.path.dirname(export_path), export_filename))

    # cleanup
    shutil.rmtree(export_path)
