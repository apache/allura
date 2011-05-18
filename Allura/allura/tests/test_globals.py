from os import path, environ

from nose.tools import with_setup

import webob
from urllib import quote
from tg import config
from paste.deploy import loadapp
from paste.script.appinstall import SetupCommand
from pylons import c, g, session, request

from alluratest.controller import setup_basic_test, setup_global_objects

from allura import model as M
from allura.lib import helpers as h


def setUp():
    """Method called by nose before running each test"""
    setup_basic_test()
    setup_global_objects()

def test_app_globals():
    g.oid_session()
    g.oid_session()
    g.set_project('test')
    g.set_app('wiki')
    assert g.app_static('css/wiki.css') == '/nf/_static_/Wiki/css/wiki.css', g.app_static('css/wiki.css')
    assert g.url('/foo', a='foo bar') == 'http://localhost:80/foo?a=foo+bar', g.url('/foo', a='foo bar')
    assert g.url('/foo') == 'http://localhost:80/foo', g.url('/foo')

@with_setup(setUp)
def test_markdown():
    'Just a test to get coverage in our markdown extension'
    g.set_project('test')
    g.set_app('wiki')
    assert '<a href=' in g.markdown.convert('# Foo!\n[Home]')
    assert '<a href=' not in g.markdown.convert('# Foo!\n[Rooted]')
    assert '<a href=' in g.markdown.convert('This is http://sf.net')
    tgt = 'http://everything2.com/?node=nate+oostendorp'
    url = '/nf/redirect/?path=%s' % quote(tgt)
    s = g.markdown.convert('This is %s' % tgt)
    assert s == '<div class="markdown_content"><p>This is <a href="%s" rel="nofollow">%s</a></p></div>' % (url, tgt), s
    assert '<a href=' in g.markdown.convert('This is http://sf.net')    
    # assert '<a href=' in g.markdown_wiki.convert('This is a WikiPage')
    # assert '<a href=' not in g.markdown_wiki.convert('This is a WIKIPAGE')
    assert '<br' in g.markdown.convert('Multi\nLine'), g.markdown.convert('Multi\nLine')
    assert '<br' not in g.markdown.convert('Multi\n\nLine')
    r = g.markdown.convert('[[projects]]')
    assert '[[projects]]' in r, r
    with h.push_context(M.Neighborhood.query.get(name='Projects').neighborhood_project()._id):
        r = g.markdown_wiki.convert('[[projects]]')
        assert '<div class="border card">' in r, r
    r = g.markdown.convert('[[include ref=Home id=foo]]')
    assert '<div id="foo">' in r, r
    assert 'href="../foo"' in g.markdown.convert('[My foo](foo)')
    assert 'href="..' not in g.markdown.convert('[My foo](./foo)')
    g.markdown.convert("<class 'foo'>") # should not raise an exception
    assert '<br>' not in g.markdown.convert('''# Header

Some text in a regular paragraph

    :::python
    for i in range(10):
        print i
''')
    assert 'http://localhost/' in  g.forge_markdown(email=True).convert('[Home]')
    assert 'class="codehilite"' in g.markdown.convert('''
~~~~
def foo(): pass
~~~~''')


