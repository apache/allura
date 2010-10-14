import ew
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
