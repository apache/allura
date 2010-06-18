import ew

class HgRevisionWidget(ew.Widget):
    template='genshi:forgehg.widgets.templates.revision'
    params=['value', 'prev', 'next']
    value=None
    prev=()
    next=()
