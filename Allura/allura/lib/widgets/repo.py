import ew
from allura.lib.widgets import form_fields as ffw

class SCMLogWidget(ew.Widget):
    template='jinja:repo_widgets/log.html'
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
    template='jinja:repo_widgets/revision.html'
    params=['value', 'prev', 'next']
    value=None
    prev=()
    next=()

class SCMTreeWidget(ew.Widget):
    template='allura.lib.widgets.templates.tree_widget'
    params=['repo', 'commit', 'tree', 'path']
    repo=commit=tree=path=None
