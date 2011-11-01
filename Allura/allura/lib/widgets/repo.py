import pylons

import ew as ew_core
import ew.jinja2_ew as ew

from allura import model as M
from allura.lib.widgets import forms as ff
from allura.lib.widgets import form_fields as ffw

class SCMLogWidget(ew_core.Widget):
    template='jinja:allura:templates/widgets/repo/log.html'
    defaults=dict(
        ew_core.Widget.defaults,
        value=None,
        limit=None,
        page=0,
        count=0,
        show_paging=True)

    class fields(ew_core.NameList):
        page_list=ffw.PageList()
        page_size=ffw.PageSize()

    def resources(self):
        for f in self.fields:
            for r in f.resources():
                yield r

class SCMRevisionWidget(ew_core.Widget):
    template='jinja:allura:templates/widgets/repo/revision.html'
    defaults=dict(
        ew_core.Widget.defaults,
        value=None,
        prev=ew_core.NoDefault,
        next=ew_core.NoDefault)

class SCMTreeWidget(ew_core.Widget):
    template='jinja:allura:templates/widgets/repo/tree_widget.html'
    defaults=dict(
        ew_core.Widget.defaults,
        tree=None,
        list=list)

class SCMMergeRequestWidget(ff.ForgeForm):
    source_branches=[]
    target_branches=[]

    @property
    def fields(self):
        result = [
            ew.TextField(name='summary'),
            ew.SingleSelectField(
                name='source_branch',
                label='Source Branch',
                options=self.source_branches),
            ew.SingleSelectField(
                name='target_branch',
                label='Target Branch',
                options=self.target_branches),
            ffw.AutoResizeTextarea(name='description') ]
        return result

class SCMMergeRequestFilterWidget(ff.ForgeForm):
    defaults=dict(
        ff.ForgeForm.defaults,
        submit_text='Filter',
        method='GET')

    class fields(ew_core.NameList):
        status=ew.MultiSelectField(options=M.MergeRequest.statuses)

class SCMMergeRequestDisposeWidget(ff.ForgeForm):

    class fields(ew_core.NameList):
        status=ew.SingleSelectField(
            label='Change Status',
            options=M.MergeRequest.statuses)

class SCMCommitBrowserWidget(ew_core.Widget):
    template='jinja:allura:templates/widgets/repo/commit_browser.html'
    defaults=dict(
        ew_core.Widget.defaults,
    )

    def resources(self):
        yield ew.JSLink('js/commit_browser.js')
        yield ew.CSSLink('css/commit_browser.css')
