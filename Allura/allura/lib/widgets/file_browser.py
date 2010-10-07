import ew

class TreeWidget(ew.Widget):
    template='jinja:tree_widget.html'
    params=['tree']
    tree=None
