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

from tg import expose, validate, flash, redirect
from tg.decorators import with_trailing_slash
from pylons import tmpl_context as c
from formencode import validators as fev, schema

from allura import model as M
from allura.lib.decorators import require_post
from allura.lib.widgets.forms import NeighborhoodProjectShortNameValidator
from allura.lib import helpers as h
from allura.lib import exceptions

from .. import base
from . import tasks



class GoogleCodeProjectForm(schema.Schema):
    neighborhood = fev.PlainText(not_empty=True)
    project_name = fev.Regex(r'^[a-z0-9][a-z0-9-]{,61}$', not_empty=True)
    project_shortname = NeighborhoodProjectShortNameValidator()
    tools = base.ToolsValidator('Google Code')


class GoogleCodeProjectImporter(base.ProjectImporter):
    source = 'Google Code'

    @with_trailing_slash
    @expose('jinja:forgeimporters.google:templates/project.html')
    def index(self, **kw):
        neighborhood = M.Neighborhood.query.get(url_prefix='/p/')
        return {'importer': self, 'neighborhood': neighborhood}

    @require_post()
    @expose()
    @validate(GoogleCodeProjectForm(), error_handler=index)
    def process(self, project_name=None, project_shortname=None, tools=None, **kw):
        neighborhood = M.Neighborhood.query.get(url_prefix='/p/')
        project_name = h.really_unicode(project_name).encode('utf-8')
        project_shortname = h.really_unicode(project_shortname).encode('utf-8').lower()

        try:
            c.project = neighborhood.register_project(project_shortname,
                    project_name=project_name)
        except exceptions.ProjectOverlimitError:
            flash("You have exceeded the maximum number of projects you are allowed to create", 'error')
            redirect('.')
        except exceptions.ProjectRatelimitError:
            flash("Project creation rate limit exceeded.  Please try again later.", 'error')
            redirect('.')
        except Exception as e:
            log.error('error registering project: %s', project_shortname, exc_info=True)
            flash('Internal Error. Please try again later.', 'error')
            redirect('.')

        c.project.set_tool_data('google-code', project_name=project_name)
        tasks.import_project_info.post()
        for tool in tools:
            tool.import_tool(c.project)

        flash('Welcome to the SourceForge Project System! '
              'Your project data will be imported and should show up here shortly.')
        redirect(c.project.script_name + 'admin/overview')

    @expose('json:')
    @validate(GoogleCodeProjectForm())
    def check_names(self, project_name=None, project_shortname=None, tools=None, **kw):
        return c.form_errors
