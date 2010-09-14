import ew

class HgRevisionWidget(ew.Widget):
    template='jinja:hg_widgets/revision.html'
    params=['value', 'prev', 'next']
    value=None
    prev=()
    next=()
