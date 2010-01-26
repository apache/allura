from os import path

from tg import config
from pylons import c, g
from paste.deploy import loadapp
from paste.script.appinstall import SetupCommand

from pyforge import model as M
from pyforge.lib import helpers as h

def setUp(self):
    """Method called by nose before running each test"""
    # Loading the application:
    conf_dir = config.here
    wsgiapp = loadapp('config:test.ini#main',
                      relative_to=conf_dir)
    # Setting it up:
    test_file = path.join(conf_dir, 'test.ini')
    cmd = SetupCommand('setup-app')
    cmd.run([test_file])

def test_find_project():
    proj, rest = h.find_project('projects/test/foo'.split('/'))
    assert proj is not None
    proj, rest = h.find_project('projects/testable/foo'.split('/'))
    assert proj is None

def test_find_executable():
    assert h.find_executable('bash') == '/bin/bash'

def test_make_users():
    r = h.make_users([None]).next()
    assert r.username == '*anonymous', r

def test_make_roles():
    g.set_project('projects/test')
    g.set_app('hello')
    u = M.User.anonymous()
    pr = u.project_role()
    assert h.make_roles([pr._id]).next() == pr

def test_context_setters():
    h.set_context('projects/test/', 'hello')
    assert c.project is not None
    assert c.app is not None
    cfg_id = c.app.config._id
    h.set_context('projects/test/', app_config_id=cfg_id)
    assert c.project is not None
    assert c.app is not None
    h.set_context('projects/test/', app_config_id=str(cfg_id))
    assert c.project is not None
    assert c.app is not None
    c.project = c.app = None
    with h.push_context('projects/test/', 'hello'):
        assert c.project is not None
        assert c.app is not None
    assert c.project == c.app == None
    with h.push_context('projects/test/', app_config_id=cfg_id):
        assert c.project is not None
        assert c.app is not None
    assert c.project == c.app == None
    with h.push_context('projects/test/', app_config_id=str(cfg_id)):
        assert c.project is not None
        assert c.app is not None
    assert c.project == c.app == None
    del c.project
    del c.app
    with h.push_context('projects/test/', app_config_id=str(cfg_id)):
        assert c.project is not None
        assert c.app is not None
    assert not hasattr(c, 'project')
    assert not hasattr(c, 'app')

def test_encode_keys():
    kw = h.encode_keys({u'foo':5})
    assert type(kw.keys()[0]) != unicode

def test_ago():
    from datetime import datetime, timedelta
    assert h.ago(datetime.utcnow() - timedelta(days=2)) == '2 days ago'

