import ew

class Include(ew.Widget):
    template='jinja:include.html'
    params=['artifact', 'attrs']
    artifact=None
    attrs = {
        'style':'width:270px;float:right;background-color:#ccc'
        }
