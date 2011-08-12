from urllib import quote

from nose.tools import with_setup
from pylons import g, c

from ming.orm import session, ThreadLocalORMSession
from alluratest.controller import setup_basic_test, setup_global_objects

from allura import model as M
from allura.lib import helpers as h

from forgewiki import model as WM
from forgeblog import model as BM


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
def test_macros():
    p_test = M.Project.query.get(shortname='test')
    p_sub1 =  M.Project.query.get(shortname='test/sub1')
    p_test.labels = [ 'test', 'root' ]
    p_sub1.labels = [ 'test', 'sub1' ]
    
    ThreadLocalORMSession.flush_all()
    
    with h.push_context(M.Neighborhood.query.get(name='Projects').neighborhood_project._id):      
        r = g.markdown_wiki.convert('[[projects]]')
        assert '<img alt="test Logo"' in r, r
        assert '<img alt="sub1 Logo"' in r, r
        r = g.markdown_wiki.convert('[[projects labels=root]]')
        assert '<img alt="test Logo"' in r, r
        assert '<img alt="sub1 Logo"' not in r, r
        r = g.markdown_wiki.convert('[[projects labels=sub1]]')
        assert '<img alt="test Logo"' not in r, r
        assert '<img alt="sub1 Logo"' in r, r
        r = g.markdown_wiki.convert('[[projects labels=test]]')
        assert '<img alt="test Logo"' in r, r
        assert '<img alt="sub1 Logo"' in r, r
        r = g.markdown_wiki.convert('[[projects labels=test,root]]')
        assert '<img alt="test Logo"' in r, r
        assert '<img alt="sub1 Logo"' not in r, r
        r = g.markdown_wiki.convert('[[projects labels=test,sub1]]')
        assert '<img alt="test Logo"' not in r, r
        assert '<img alt="sub1 Logo"' in r, r
        r = g.markdown_wiki.convert('[[projects labels=root|sub1]]')
        assert '<img alt="test Logo"' in r, r
        assert '<img alt="sub1 Logo"' in r, r
        r = g.markdown_wiki.convert('[[projects labels=test,root|root,sub1]]')
        assert '<img alt="test Logo"' in r, r
        assert '<img alt="sub1 Logo"' not in r, r
        r = g.markdown_wiki.convert('[[projects labels=test,root|test,sub1]]')
        assert '<img alt="test Logo"' in r, r
        assert '<img alt="sub1 Logo"' in r, r
        
    r = g.markdown_wiki.convert('[[project_admins]]')
    assert r == '<div class="markdown_content"><p><a href="/u/test-admin/">Test Admin</a><br /></p></div>'
    r = g.markdown_wiki.convert('[[download_button]]')
    assert r == '<div class="markdown_content"><p><div class="download-button-test" style="margin-bottom: 1em;"></div></p></div>'
    g.set_project(M.Project.query.get(name='Home Project for Projects'))
    g.set_app('home')
    r = g.markdown_wiki.convert('[[neighborhood_feeds tool_name=Wiki]]')
    assert 'WikiPage Home modified by' in r, r
    orig_len = len(r)
    # Make project private & verify we don't see its new feed items
    proj = M.Project.query.get(shortname='test')
    c.user = M.User.anonymous()
    proj.acl.insert(0, M.ACE.deny(
            c.user.project_role(proj)._id, 'read'))
    ThreadLocalORMSession.flush_all()
    pg = WM.Page.query.get(title='Home', app_config_id=c.app.config._id)
    pg.text = 'Change'
    pg.commit()
    r = g.markdown_wiki.convert('[[neighborhood_feeds tool_name=Wiki]]')
    new_len = len(r)
    assert new_len == orig_len
    p = BM.BlogPost(title='test me', neighborhood_id=p_test.neighborhood_id)
    p.text = 'test content'
    p.state = 'published'
    p.make_slug()
    p.commit()
    ThreadLocalORMSession.flush_all()
    r = g.markdown_wiki.convert('[[neighborhood_blog_posts]]')
    assert 'test content' in r

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
    with h.push_context(M.Neighborhood.query.get(name='Projects').neighborhood_project._id):
        r = g.markdown_wiki.convert('[[projects]]')
        assert '<div class="border card">' in r, r
    r = g.markdown.convert('[[include ref=Home id=foo]]')
    assert '<div id="foo">' in r, r
    assert 'href="../foo"' in g.markdown.convert('[My foo](foo)')
    assert 'href="..' not in g.markdown.convert('[My foo](./foo)')
    g.set_project(M.Project.query.get(name='Home Project for Projects'))
    g.set_app('wiki')
    r = g.markdown_wiki.convert('[[neighborhood_feeds tool_name=Wiki]]')
    assert 'WikiPage Home modified by Test Admin' in r, r
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


