from pylons import g
from formencode.variabledecode import variable_encode

from ming.orm.ormsession import ThreadLocalORMSession

from pyforge.tests import TestController
from pyforge import model as M

class TestProjectHome(TestController):

    def test_home(self):
        r0 = str(self.app.get('/home/'))
        r = self.app.get('/home/configuration')
        selects = r.html.findAll('select')
        options = selects[-1].findAll('option')
        wnames = [
            o['value'] for o in options ]
        params = variable_encode(dict(
                divs=[
                    dict(name='content',
                         content=[ dict(widget=wn) for wn in wnames ])
                    ]))
        self.app.post('/home/update_configuration', params=params)
        r1 = str(self.app.get('/home/'))
        assert r0 != r1


