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

from io import BytesIO

import six
from tg import expose
from tg.decorators import without_trailing_slash, with_trailing_slash
from webob import exc

from tg import app_globals as g
from allura.lib import helpers as h
from allura.lib import utils


class NewForgeController:

    # /nf/_static_/... (or whatever static.script_name is set to) is handled by StaticFilesMiddleware
    # /nf/admin/... is handled by SiteAdminController

    @expose()
    @without_trailing_slash
    def markdown_to_html(self, markdown, neighborhood=None, project=None, app=None):
        """Convert markdown to html."""
        if neighborhood is None or project is None:
            raise exc.HTTPBadRequest()
        h.set_context(project, app, neighborhood=neighborhood)

        if app == 'wiki':
            html = g.markdown_wiki.convert(markdown)
        else:
            html = g.markdown.convert(markdown)
        return html

    @expose()
    def tool_icon_css(self, *args, **kw):
        """
        Serve stylesheet containing icon urls for every installed tool.

        If you want to use this, include it in your theme like:
            g.register_css('/nf/tool_icon_css?' + g.build_key, compress=False)

        """
        css, md5 = g.tool_icon_css
        return utils.serve_file(
            BytesIO(six.ensure_binary(css)), 'tool_icon_css', 'text/css', etag=md5)

    @expose('jinja:allura:templates/markdown_syntax.html')
    def markdown_syntax(self, **kw):
        'Static page explaining markdown.'
        return dict()

    @expose('jinja:allura:templates/markdown_syntax_dialog.html')
    def markdown_syntax_dialog(self, **kw):
        'Static dialog page about how to use markdown.'
        return dict()
