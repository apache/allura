import ew

class GitRevisionWidget(ew.Widget):
    template='genshi:forgegit.widgets.templates.revision'
    params=['value', 'prev', 'next']
    value=None
    prev=()
    next=()
