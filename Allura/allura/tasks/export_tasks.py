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

import tg
from pylons import app_globals as g, tmpl_context as c

from allura.tasks import mail_tasks
from allura.lib.decorators import task
from allura.lib import helpers as h
from allura.model.repository import zipdir


log = logging.getLogger(__name__)


@task
def bulk_export(tools, filename=None, send_email=True, with_attachments=False):
    '''
    Export the current project data.  Send notification to current user.

    :param list tools: list of mount_points to export
    :param str filename: optional filename to use
    '''
    # it's very handy to use c.* within a @task,
    # but let's be explicit and keep it separate from the main code
    return BulkExport().process(c.project, tools, c.user, filename, send_email, with_attachments)


class BulkExport(object):

    def process(self, project, tools, user, filename=None, send_email=True, with_attachments=False):
        export_filename = filename or project.bulk_export_filename()
        export_path = self.get_export_path(
            project.bulk_export_path(), export_filename)
        if not os.path.exists(export_path):
            os.makedirs(export_path)
        apps = [project.app_instance(tool) for tool in tools]
        exportable = self.filter_exportable(apps)
        results = [self.export(export_path, app, with_attachments) for app in exportable]
        exported = self.filter_successful(results)
        if exported:
            zipdir(export_path,
                   os.path.join(os.path.dirname(export_path), export_filename))
        shutil.rmtree(export_path)

        if not user:
            log.info('No user. Skipping notification.')
            return
        if not send_email:
            return

        tmpl = g.jinja2_env.get_template(
            'allura:templates/mail/bulk_export.html')
        instructions = tg.config.get('bulk_export_download_instructions', '')
        instructions = instructions.format(
            project=project.shortname,
            filename=export_filename,
            c=c,
        )
        exported_names = [a.config.options.mount_point for a in exported]
        tmpl_context = {
            'instructions': instructions,
            'project': project,
            'tools': exported_names,
            'not_exported_tools': list(set(tools) - set(exported_names)),
        }

        email = {
            'toaddr': unicode(user._id),
            'fromaddr': unicode(tg.config['forgemail.return_path']),
            'sender': unicode(tg.config['forgemail.return_path']),
            'reply_to': unicode(tg.config['forgemail.return_path']),
            'message_id': h.gen_message_id(),
            'subject': u'Bulk export for project %s completed' % project.shortname,
            'text': tmpl.render(tmpl_context)
        }

        mail_tasks.sendsimplemail.post(**email)

    def get_export_path(self, export_base_path, export_filename):
        """Create temporary directory for export files"""
        # Name temporary directory after project shortname,
        # thus zipdir() will use proper prefix inside the archive.
        tmp_dir_suffix = os.path.splitext(export_filename)[0]
        path = os.path.join(export_base_path, tmp_dir_suffix)
        return path

    def filter_exportable(self, apps):
        return [app for app in apps if app and app.exportable]

    def export(self, export_path, app, with_attachments=False):
        tool = app.config.options.mount_point
        json_file = os.path.join(export_path, '%s.json' % tool)
        try:
            with open(json_file, 'w') as f:
                app.bulk_export(f, export_path, with_attachments)
        except Exception:
            log.error('Error exporting: %s on %s', tool,
                      app.project.shortname, exc_info=True)
            try:
                os.remove(json_file)
            except:
                pass
            return None
        else:
            return app

    def filter_successful(self, results):
        return [result for result in results if result is not None]
