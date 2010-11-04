import pylons

import ew
from allura.lib.widgets import forms as ff
from allura.lib.widgets import form_fields as ffw

class SCMLogWidget(ew.Widget):
    template='jinja:widgets/repo/log.html'
    params=['value', 'limit', 'page', 'count', 'show_paging', 'fields']
    value=None
    limit=None
    page=0
    count=0
    show_paging=True

    class fields(ew.WidgetsList):
        page_list=ffw.PageList()
        page_size=ffw.PageSize()

    def resources(self):
        for f in self.fields:
            for r in f.resources():
                yield r

class SCMRevisionWidget(ew.Widget):
    template='jinja:widgets/repo/revision.html'
    params=['value', 'prev', 'next']
    value=None
    prev=()
    next=()

class SCMTreeWidget(ew.Widget):
    template='jinja:widgets/repo/tree_widget.html'
    params=['tree', 'list']
    tree=None

    def __init__(self, **kw):
        super(SCMTreeWidget, self).__init__(**kw)
        self.list = list

class SCMMergeRequestWidget(ff.ForgeForm):
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
