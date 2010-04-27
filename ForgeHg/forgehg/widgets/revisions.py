import ew

class HgRevisionWidget(ew.Widget):
    template='genshi:forgehg.widgets.templates.revision'
    params=['value']
    value=None
