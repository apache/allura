import ew

class HgRevisionWidget(ew.Widget):
    template='jinja:hg_revision_widget.html'
    params=['value', 'prev', 'next']
    value=None
    prev=()
    next=()
