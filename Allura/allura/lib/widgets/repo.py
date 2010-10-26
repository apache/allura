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
    class fields(ew.WidgetsList):
        summary=ew.TextField()
        branch=ew.SingleSelectField(
            label='Branch or Tag',
            options=lambda:[
                b.name
                for b in pylons.c.app.repo.branches + pylons.c.app.repo.tags])
        description=ffw.AutoResizeTextarea()
