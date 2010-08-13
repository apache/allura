import ew

class Include(ew.Widget):
    template='genshi:allura.lib.widgets.templates.include'
    params=['artifact', 'attrs']
    artifact=None
    attrs = {
        'style':'width:270px;float:right;background-color:#ccc'
        }
