import ew

class SVNRevisionWidget(ew.Widget):
    template='genshi:forgesvn.widgets.templates.revision'
    params=['value']
    value=None
