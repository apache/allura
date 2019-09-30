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

import pkg_resources
from tg import tmpl_context as c
from tg import expose, validate
from tg.decorators import with_trailing_slash
from formencode import validators as V

from allura.app import Application
from allura import version
from allura.lib.search import search_app
from allura.lib.widgets.search import SearchResults, SearchHelp
from allura.controllers import BaseController

log = logging.getLogger(__name__)


class SearchApp(Application):

    '''This is the HelloWorld application for Allura, showing
    all the rich, creamy goodness that is installable apps.
    '''
    __version__ = version.__version__
    max_instances = 0
    hidden = True
    has_notifications = False
    sitemap = []

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = SearchController()
        self.templates = pkg_resources.resource_filename(
            'allura.ext.search', 'templates')

    def main_menu(self):  # pragma no cover
        return []

    def sidebar_menu(self):  # pragma no cover
        return []

    def admin_menu(self):  # pragma no cover
        return []

    def install(self, project):
        pass  # pragma no cover

    def uninstall(self, project):
        pass  # pragma no cover


class SearchController(BaseController):

    @expose('jinja:allura:templates/search_index.html')
    @validate(dict(q=V.UnicodeString(),
                   history=V.StringBool(if_empty=False)))
    @with_trailing_slash
    def index(self, q=None, history=None, **kw):
        c.search_results = SearchResults()
        c.help_modal = SearchHelp(comments=False)
        pids = [c.project._id] + [p._id for p in c.project.subprojects]
        project_match = ' OR '.join(map(str, pids))
        search_params = kw
        search_params.update({
            'q': q,
            'history': history,
            'app': False,
            'fq': [
                'project_id_s:(%s)' % project_match,
                '-deleted_b:true',
            ],
        })
        d = search_app(**search_params)
        d['search_comments_disable'] = True
        d['hide_app_project_switcher'] = True
        return d
