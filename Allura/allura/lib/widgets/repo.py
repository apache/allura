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

from allura import model as M
from allura.lib.widgets import forms as ff
from allura.lib.widgets import form_fields as ffw


class SCMLogWidget(ew_core.Widget):
    template = 'jinja:allura:templates/widgets/repo/log.html'
    defaults = dict(
        ew_core.Widget.defaults,
        value=None,
        limit=None,
        page=0,
        count=0,
        show_paging=True)

    class fields(ew_core.NameList):
        page_list = ffw.PageList()
        page_size = ffw.PageSize()

    def resources(self):
        for f in self.fields:
            yield from f.resources()


class SCMRevisionWidget(ew_core.Widget):
    template = 'jinja:allura:templates/widgets/repo/revision.html'
    defaults = dict(
        ew_core.Widget.defaults,
        value=None,
        prev=ew_core.NoDefault,
        next=ew_core.NoDefault)


class SCMTreeWidget(ew_core.Widget):
    template = 'jinja:allura:templates/widgets/repo/tree_widget.html'
    defaults = dict(
        ew_core.Widget.defaults,
        tree=None,
        list=list)


class SCMMergeRequestWidget(ff.ForgeForm):
    source_branches = []
    target_branches = []
    show_subscribe_checkbox = False

    @property
    def fields(self):
        result = [
            ew.TextField(
                name='summary',
                attrs={'style': 'width: 93.5%;'}),
            ew.SingleSelectField(
                name='source_branch',
                label='Source Branch',
                options=self.source_branches),
            ew.SingleSelectField(
                name='target_branch',
                label='Target Branch',
                options=self.target_branches),
            ffw.MarkdownEdit(name='description')]
        return result

    @property
    def buttons(self):
        # add things after the default submit button
        fields = ew_core.NameList()
        if self.show_subscribe_checkbox:
            fields.append(ew.Checkbox(name='subscribe', label='Subscribe to this merge request', value=True,
                                      attrs={'class': 'subscribe-checkbox'}))
        return fields


class SCMMergeRequestDisposeWidget(ff.ForgeForm):

    class fields(ew_core.NameList):
        status = ew.SingleSelectField(
            label='Change Status',
            options=M.MergeRequest.statuses)


class SCMCommitBrowserWidget(ew_core.Widget):
    template = 'jinja:allura:templates/widgets/repo/commit_browser.html'
    defaults = dict(
        ew_core.Widget.defaults,
    )

    def resources(self):
        yield ew.JSLink('allura/js/hidpi-canvas.min.js')
        yield ew.JSLink('js/commit_browser.js')
        yield ew.CSSLink('css/commit_browser.css')
