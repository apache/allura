from os import path, environ

from tg import config
from pylons import c, g
from paste.deploy import loadapp
from paste.script.appinstall import SetupCommand
from nose.tools import eq_

from allura import model as M
from allura.lib import helpers as h

from alluratest.controller import setup_basic_test


def setUp(self):
    """Method called by nose before running each test"""
    setup_basic_test()

def test_really_unicode():
    here_dir = path.dirname(__file__)
    s = h.really_unicode('\xef\xbb\xbf<?xml version="1.0" encoding="utf-8" ?>')
    assert s.startswith(u'\ufeff')
    s = h.really_unicode(open(path.join(here_dir, 'data/unicode_test.txt')).read())
    assert isinstance(s, unicode)

def test_render_genshi_plaintext():
    here_dir = path.dirname(__file__)
    tpl = path.join(here_dir, 'data/genshi_hello_tmpl')
    text = h.render_genshi_plaintext(tpl, object='world')
    eq_(u'Hello, world!\n', text)

def test_find_project():
    proj, rest = h.find_project('/p/test/foo')
    assert proj is not None
    proj, rest = h.find_project('/p/testable/foo')
    assert proj is None

def test_find_executable():
    assert h.find_executable('bash') == '/bin/bash'

def test_make_users():
    r = h.make_users([None]).next()
    assert r.username == '*anonymous', r

def test_make_roles():
    g.set_project('test')
    g.set_app('wiki')
    u = M.User.anonymous()
    pr = u.project_role()
    assert h.make_roles([pr._id]).next() == pr

def test_context_setters():
    h.set_context('test', 'wiki')
    assert c.project is not None
    assert c.app is not None
    cfg_id = c.app.config._id
    h.set_context('test', app_config_id=cfg_id)
    assert c.project is not None
    assert c.app is not None
    h.set_context('test', app_config_id=str(cfg_id))
    assert c.project is not None
    assert c.app is not None
    c.project = c.app = None
    with h.push_context('test', 'wiki'):
        assert c.project is not None
        assert c.app is not None
    assert c.project == c.app == None
    with h.push_context('test', app_config_id=cfg_id):
        assert c.project is not None
        assert c.app is not None
    assert c.project == c.app == None
    with h.push_context('test', app_config_id=str(cfg_id)):
        assert c.project is not None
        assert c.app is not None
    assert c.project == c.app == None
    del c.project
    del c.app
    with h.push_context('test', app_config_id=str(cfg_id)):
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

