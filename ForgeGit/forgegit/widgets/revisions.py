import ew

class GitRevisionWidget(ew.Widget):
    template='genshi:forgegit.widgets.templates.revision'
    params=['value']
    value=None
