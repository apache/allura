from os import path

from pylons import c
from nose.tools import eq_, assert_equals

from allura import model as M
from allura.lib import helpers as h
from allura.tests import decorators as td
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
    # try non-ascii string in legacy 8bit encoding
    h.really_unicode(u'\u0410\u0401'.encode('cp1251'))

def test_render_genshi_plaintext():
    here_dir = path.dirname(__file__)
    tpl = path.join(here_dir, 'data/genshi_hello_tmpl')
    text = h.render_genshi_plaintext(tpl, object='world')
    eq_(u'Hello, world!\n', text)

def test_find_project():
    proj, rest = h.find_project('/p/test/foo')
    assert_equals(proj.shortname, 'test')
    assert_equals(proj.neighborhood.name, 'Projects')
    proj, rest = h.find_project('/p/testable/foo')
    assert proj is None

def test_find_executable():
    assert h.find_executable('bash') == '/bin/bash'

def test_make_users():
    r = h.make_users([None]).next()
    assert r.username == '*anonymous', r

def test_make_roles():
    h.set_context('test', 'wiki', neighborhood='Projects')
    u = M.User.anonymous()
    pr = u.project_role()
    assert h.make_roles([pr._id]).next() == pr

@td.with_wiki
def test_context_setters():
    h.set_context('test', 'wiki', neighborhood='Projects')
    assert c.project is not None
    assert c.app is not None
    cfg_id = c.app.config._id
    h.set_context('test', app_config_id=cfg_id, neighborhood='Projects')
    assert c.project is not None
    assert c.app is not None
    h.set_context('test', app_config_id=str(cfg_id), neighborhood='Projects')
    assert c.project is not None
    assert c.app is not None
    c.project = c.app = None
    with h.push_context('test', 'wiki', neighborhood='Projects'):
        assert c.project is not None
        assert c.app is not None
    assert c.project == c.app == None
    with h.push_context('test', app_config_id=cfg_id, neighborhood='Projects'):
        assert c.project is not None
        assert c.app is not None
    assert c.project == c.app == None
    with h.push_context('test', app_config_id=str(cfg_id), neighborhood='Projects'):
        assert c.project is not None
        assert c.app is not None
    assert c.project == c.app == None
    del c.project
    del c.app
    with h.push_context('test', app_config_id=str(cfg_id), neighborhood='Projects'):
        assert c.project is not None
        assert c.app is not None
    assert not hasattr(c, 'project')
    assert not hasattr(c, 'app')

def test_encode_keys():
    kw = h.encode_keys({u'foo':5})
    assert type(kw.keys()[0]) != unicode

def test_ago():
    from datetime import datetime, timedelta
    import time
    assert_equals(h.ago(datetime.utcnow() - timedelta(days=2)), '2 days ago')
    assert_equals(h.ago_ts(time.time() - 60*60*2), '2 hours ago')

def test_urlquote_unicode():
    # No exceptions please
    h.urlquote(u'\u0410')
    h.urlquoteplus(u'\u0410')

def test_sharded_path():
    assert_equals(h.sharded_path('foobar'), 'f/fo')

def test_paging_sanitizer():
    test_data = {
        # input (limit, page, total, zero-based): output (limit, page)
        (0, 0, 0): (1, 0),
        ('1', '1', 1): (1, 0),
        (5, '10', 25): (5, 4),
        ('5', 10, 25, False): (5, 5),
        (5, '-1', 25): (5, 0),
        ('5', -1, 25, False): (5, 1),
        (5, '3', 25): (5, 3),
        ('5', 3, 25, False): (5, 3)
    }
    for input, output in test_data.iteritems():
        assert (h.paging_sanitizer(*input)) == output
