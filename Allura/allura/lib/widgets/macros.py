import ew

class Include(ew.Widget):
    template='jinja:widgets/include.html'
    params=['artifact', 'attrs']
    artifact=None
    attrs = {
        'style':'width:270px;float:right;background-color:#ccc'
        }
