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

import ew as ew_core
import ew.jinja2_ew as ew
import jinja2

from allura.lib.widgets import form_fields as ffw


class SearchResults(ew_core.Widget):
    template = 'jinja:allura:templates/widgets/search_results.html'
    defaults = dict(
        ew_core.Widget.defaults,
        results=None,
        limit=None,
        page=0,
        count=0,
        search_error=None)

    class fields(ew_core.NameList):
        page_list = ffw.PageList()
        page_size = ffw.PageSize()

    def resources(self):
        for f in self.fields:
            yield from f.resources()
        yield ew.CSSLink('css/search.css')


class SearchHelp(ffw.Lightbox):
    defaults = dict(
        ffw.Lightbox.defaults,
        name='search_help_modal',
        trigger='a.search_help_modal')

    def __init__(self, comments=True, history=True, fields={}):
        super().__init__()
        # can't use g.jinja2_env since this widget gets imported too early :(
        jinja2_env = jinja2.Environment(
            loader=jinja2.PackageLoader('allura', 'templates/widgets'))
        self.content = jinja2_env.get_template('search_help.html').render(dict(
            comments=comments,
            history=history,
            fields=fields,
        ))
