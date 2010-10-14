import ew

class TreeWidget(ew.Widget):
    template='jinja:widgets/tree_widget.html'
    params=['tree']
    tree=None
