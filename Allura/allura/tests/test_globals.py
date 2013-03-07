# -*- coding: utf-8 -*-

import re
import os, allura
from mock import patch
from urllib import quote

from bson import ObjectId

from nose.tools import with_setup, assert_equal, assert_in, assert_not_in
from pylons import tmpl_context as c, app_globals as g

from ming.orm import ThreadLocalORMSession
from alluratest.controller import setup_basic_test, setup_global_objects

from allura import model as M
from allura.lib import helpers as h
from allura.tests import decorators as td

from forgewiki import model as WM
from forgeblog import model as BM


def setUp():
    """Method called by nose once before running the package.  Some functions need it run again to reset data"""
    setup_basic_test()
    setup_with_tools()

@td.with_wiki
def setup_with_tools():
    setup_global_objects()

@td.with_wiki
def test_app_globals():
    g.oid_session()
    g.oid_session()
    with h.push_context('test', 'wiki', neighborhood='Projects'):
        assert g.app_static('css/wiki.css') == '/nf/_static_/wiki/css/wiki.css', g.app_static('css/wiki.css')
        assert g.url('/foo', a='foo bar') == 'http://localhost:80/foo?a=foo+bar', g.url('/foo', a='foo bar')
        assert g.url('/foo') == 'http://localhost:80/foo', g.url('/foo')


@with_setup(teardown=setUp) # reset everything we changed
def test_macros():
    file_name = 'neo-icon-set-454545-256x350.png'
    file_path = os.path.join(allura.__path__[0],'nf','allura','images',file_name)
    curr_project = c.project

    p_nbhd = M.Neighborhood.query.get(name='Projects')
    p_test = M.Project.query.get(shortname='test', neighborhood_id=p_nbhd._id)
    c.project = p_test
    icon_file = open(file_path)
    M.ProjectFile.save_image(
                file_name, icon_file, content_type='image/png',
                square=True, thumbnail_size=(48,48),
                thumbnail_meta=dict(project_id=c.project._id,category='icon'))
    icon_file.close()
    p_test2 = M.Project.query.get(shortname='test2', neighborhood_id=p_nbhd._id)
    c.project = p_test2
    icon_file = open(file_path)
    M.ProjectFile.save_image(
                file_name, icon_file, content_type='image/png',
                square=True, thumbnail_size=(48,48),
                thumbnail_meta=dict(project_id=c.project._id,category='icon'))
    icon_file.close()
    p_sub1 =  M.Project.query.get(shortname='test/sub1', neighborhood_id=p_nbhd._id)
    c.project = p_sub1
    icon_file = open(file_path)
    M.ProjectFile.save_image(
                file_name, icon_file, content_type='image/png',
                square=True, thumbnail_size=(48,48),
                thumbnail_meta=dict(project_id=c.project._id,category='icon'))
    icon_file.close()
    p_test.labels = [ 'test', 'root' ]
    p_sub1.labels = [ 'test', 'sub1' ]
    # Make one project private
    p_test.private = False
    p_sub1.private = False
    p_test2.private = True

    ThreadLocalORMSession.flush_all()

    with h.push_context(p_nbhd.neighborhood_project._id):
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
        r = g.markdown_wiki.convert('[[projects show_total=True sort=random]]')
        assert '<p class="macro_projects_total">3 Projects</p>' in r, r
        r = g.markdown_wiki.convert('[[projects show_total=True private=True sort=random]]')
        assert '<p class="macro_projects_total">1 Projects</p>' in r, r
        assert '<img alt="test2 Logo"' in r, r
        assert '<img alt="test Logo"' not in r, r
        assert '<img alt="sub1 Logo"' not in r, r

        r = g.markdown_wiki.convert('[[projects show_proj_icon=True]]')
        assert '<img alt="test Logo"' in r
        r = g.markdown_wiki.convert('[[projects show_proj_icon=False]]')
        assert '<img alt="test Logo"' not in r

    c.project = curr_project
    r = g.markdown_wiki.convert('[[download_button]]')
    assert_equal(r, '<div class="markdown_content"><p><span class="download-button-%s" style="margin-bottom: 1em; display: block;"></span></p>\n</div>' % p_test._id)
    h.set_context('--init--', 'wiki', neighborhood='Projects')
    r = g.markdown_wiki.convert('[[neighborhood_feeds tool_name=Wiki]]')
    assert 'WikiPage Home modified by' in r, r
    orig_len = len(r)
    # Make project private & verify we don't see its new feed items
    proj = M.Project.query.get(shortname='test', neighborhood_id=p_nbhd._id)
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

def test_macro_project_admins():
    user = M.User.by_username('test-admin')
    user.display_name = u'Test Ådmin'
    r = g.markdown_wiki.convert('[[project_admins]]')
    assert_equal(r, u'<div class="markdown_content"><p><a href="/u/test-admin/">Test Ådmin</a><br /></p>\n</div>')

def test_macro_project_admins_one_br():
    p_nbhd = M.Neighborhood.query.get(name='Projects')
    p_test = M.Project.query.get(shortname='test', neighborhood_id=p_nbhd._id)
    p_test.add_user(M.User.by_username('test-user'), ['Admin'])
    ThreadLocalORMSession.flush_all()
    r = g.markdown_wiki.convert('[[project_admins]]\n[[download_button]]')
    assert not '</a><br /><br /><a href=' in r, r
    assert '</a><br /><a href=' in r, r


@td.with_wiki
def test_macro_include_extra_br():
    p_nbhd = M.Neighborhood.query.get(name='Projects')
    p_test = M.Project.query.get(shortname='test', neighborhood_id=p_nbhd._id)
    wiki = p_test.app_instance('wiki')
    with h.push_context(p_test._id, app_config_id=wiki.config._id):
        p = WM.Page.upsert(title='Include_1')
        p.text = 'included page 1'
        p.commit()
        p = WM.Page.upsert(title='Include_2')
        p.text = 'included page 2'
        p.commit()
        p = WM.Page.upsert(title='Include_3')
        p.text = 'included page 3'
        p.commit()
        ThreadLocalORMSession.flush_all()
        md = '[[include ref=Include_1]]\n[[include ref=Include_2]]\n[[include ref=Include_3]]'
        html = g.markdown_wiki.convert(md)

    expected_html = '''
<div class="markdown_content">
<p>
<div><div class="markdown_content"><p>included page 1</p></div></div>
<div><div class="markdown_content"><p>included page 2</p></div></div>
<div><div class="markdown_content"><p>included page 3</p></div></div>
</p>
</div>
'''.strip().replace('\n', '')
    assert html.strip().replace('\n', '') == expected_html, html


def test_markdown_toc():
    r = g.markdown_wiki.convert("""[TOC]

# Header 1

## Header 2""")
    assert '''<ul>
<li><a href="#header-1">Header 1</a><ul>
<li><a href="#header-2">Header 2</a></li>
</ul>
</li>
</ul>''' in r, r


@td.with_wiki
def test_wiki_artifact_links():
    text = g.markdown.convert('See [18:13:49]')
    assert 'See <span>[18:13:49]</span>' in text, text
    with h.push_context('test', 'wiki', neighborhood='Projects'):
        text = g.markdown.convert('Read [here](Home) about our project')
        assert '<a class="" href="/p/test/wiki/Home/">here</a>' in text, text
        text = g.markdown.convert('[Go home](test:wiki:Home)')
        assert '<a class="" href="/p/test/wiki/Home/">Go home</a>' in text, text
        text = g.markdown.convert('See [test:wiki:Home]')
        assert '<a class="alink" href="/p/test/wiki/Home/">[test:wiki:Home]</a>' in text, text

def test_markdown_links():
    text = g.markdown.convert('Read [here](http://foobar.sf.net/) about our project')
    assert_in('href="http://foobar.sf.net/">here</a> about', text)

    text = g.markdown.convert('Read [here](/p/foobar/blah) about our project')
    assert_in('href="/p/foobar/blah">here</a> about', text)

    text = g.markdown.convert('Read <http://foobar.sf.net/> about our project')
    assert_in('href="http://foobar.sf.net/">http://foobar.sf.net/</a> about', text)

def test_markdown_and_html():
    r = g.markdown_wiki.convert('<div style="float:left">blah</div>')
    assert '<div style="float: left;">blah</div>' in r, r


def test_markdown_within_html():
    r = g.markdown_wiki.convert('<div style="float:left" markdown>**blah**</div>')
    assert '''<div style="float: left;">
<p><strong>blah</strong></p>
</div>''' in r, r


@td.with_wiki
def test_markdown_basics():
    with h.push_context('test', 'wiki', neighborhood='Projects'):
        text = g.markdown.convert('# Foo!\n[Home]')
        assert '<a class="alink" href=' in text, text
        text = g.markdown.convert('# Foo!\n[Rooted]')
        assert '<a href=' not in text, text

    assert '<br' in g.markdown.convert('Multi\nLine'), g.markdown.convert('Multi\nLine')
    assert '<br' not in g.markdown.convert('Multi\n\nLine')

    g.markdown.convert("<class 'foo'>")  # should not raise an exception
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


def test_markdown_autolink():
    tgt = 'http://everything2.com/?node=nate+oostendorp'
    s = g.markdown.convert('This is %s' % tgt)
    assert_equal(
        s, '<div class="markdown_content"><p>This is <a href="%s" rel="nofollow">%s</a></p></div>' % (tgt, tgt))
    assert '<a href=' in g.markdown.convert('This is http://sf.net')
    # beginning of doc
    assert_in('<a href=', g.markdown.convert('http://sf.net abc'))
    # beginning of a line
    assert_in('<br />\n<a href="http://', g.markdown.convert('foobar\nhttp://sf.net abc'))
    # no conversion of these urls:
    assert_in('a blahttp://sdf.com z',
              g.markdown.convert('a blahttp://sdf.com z'))
    assert_in('literal <code>http://sf.net</code> literal',
              g.markdown.convert('literal `http://sf.net` literal'))
    assert_in('<pre>preformatted http://sf.net\n</pre>',
              g.markdown.convert('    :::text\n'
                                 '    preformatted http://sf.net'))


def test_markdown_autolink_with_escape():
    # \_ is unnecessary but valid markdown escaping and should be considered as a regular underscore
    # (it occurs during html2text conversion during project migrations)
    r = g.markdown.convert('a http://www.phpmyadmin.net/home\_page/security/\#target b')
    assert 'href="http://www.phpmyadmin.net/home_page/security/#target"' in r, r


def test_macro_projects():
    r = g.markdown.convert('[[projects]]')
    assert '[[projects]]' in r, r
    with h.push_context(M.Neighborhood.query.get(name='Projects').neighborhood_project._id):
        r = g.markdown_wiki.convert('[[projects]]')
        assert '<div class="border card">' in r, r

@td.with_wiki
def test_macro_include():
    r = g.markdown.convert('[[include ref=Home id=foo]]')
    assert '<div id="foo">' in r, r
    assert 'href="../foo"' in g.markdown.convert('[My foo](foo)')
    assert 'href="..' not in g.markdown.convert('[My foo](./foo)')


def test_macro_nbhd_feeds():
    with h.push_context('--init--', 'wiki', neighborhood='Projects'):
        r = g.markdown_wiki.convert('[[neighborhood_feeds tool_name=Wiki]]')
        assert 'WikiPage Home modified by ' in r, r


def test_sort_alpha():
    p_nbhd = M.Neighborhood.query.get(name='Projects')

    with h.push_context(p_nbhd.neighborhood_project._id):
        r = g.markdown_wiki.convert('[[projects sort=alpha]]')
        project_list = get_project_names(r)
        assert project_list == sorted(project_list)


def test_sort_registered():
    p_nbhd = M.Neighborhood.query.get(name='Projects')

    with h.push_context(p_nbhd.neighborhood_project._id):
        r = g.markdown_wiki.convert('[[projects sort=last_registered]]')
        project_names = get_project_names(r)
        ids = get_projects_property_in_the_same_order(project_names, '_id')
        assert ids == sorted(ids, reverse=True)


def test_sort_updated():
    p_nbhd = M.Neighborhood.query.get(name='Projects')

    with h.push_context(p_nbhd.neighborhood_project._id):
        r = g.markdown_wiki.convert('[[projects sort=last_updated]]')
        project_names = get_project_names(r)
        updated_at = get_projects_property_in_the_same_order(project_names, 'last_updated')
        assert updated_at == sorted(updated_at, reverse=True)


def test_filtering():
    # set up for test
    from random import choice
    random_trove = choice(M.TroveCategory.query.find().all())
    test_project = M.Project.query.get(name='test')
    test_project_troves = getattr(test_project, 'trove_' + random_trove.type)
    test_project_troves.append(random_trove._id)
    ThreadLocalORMSession.flush_all()

    p_nbhd = M.Neighborhood.query.get(name='Projects')
    with h.push_context(p_nbhd.neighborhood_project._id):
        r = g.markdown_wiki.convert('[[projects category="%s"]]' % random_trove.fullpath)
        project_names = get_project_names(r)
        assert [test_project.name, ] == project_names


def test_projects_macro():
    two_column_style = 'width: 330px;'

    p_nbhd = M.Neighborhood.query.get(name='Projects')
    with h.push_context(p_nbhd.neighborhood_project._id):
        # test columns
        r = g.markdown_wiki.convert('[[projects display_mode=list columns=2]]')
        assert two_column_style in r
        r = g.markdown_wiki.convert('[[projects display_mode=list columns=3]]')
        assert two_column_style not in r

        # test project download button
        r = g.markdown_wiki.convert('[[projects display_mode=list show_download_button=True]]')
        assert 'download-button' in r
        r = g.markdown_wiki.convert('[[projects display_mode=list show_download_button=False]]')
        assert 'download-button' not in r


@td.with_wiki
def test_limit_tools_macro():
    p_nbhd = M.Neighborhood.query.get(name='Adobe')
    with h.push_context(p_nbhd.neighborhood_project._id, 'wiki'):
        r = g.markdown_wiki.convert('[[projects]]')
        assert '<span>Admin</span>' in r
        r = g.markdown_wiki.convert('[[projects grid_view_tools=wiki]]')
        assert '<span>Admin</span>' not in r
        r = g.markdown_wiki.convert('[[projects grid_view_tools=wiki,admin]]')
        assert '<span>Admin</span>' in r

@td.with_user_project('test-admin')
@td.with_user_project('test-user-1')
def test_myprojects_macro():
    h.set_context('u/%s' % (c.user.username), 'wiki', neighborhood='Users')
    r = g.markdown_wiki.convert('[[my_projects]]')
    for p in c.user.my_projects():
        if p.deleted or p.is_nbhd_project:
            continue
        proj_title = '<h2><a href="%s">%s</a></h2>' % (p.url(), p.name)
        assert proj_title in r

    h.set_context('u/test-user-1', 'wiki', neighborhood='Users')
    user = M.User.query.get(username='test-user-1')
    r = g.markdown_wiki.convert('[[my_projects]]')
    for p in user.my_projects():
        if p.deleted or p.is_nbhd_project:
            continue
        proj_title = '<h2><a href="%s">%s</a></h2>' % (p.url(), p.name)
        assert proj_title in r


@td.with_wiki
def test_hideawards_macro():
    p_nbhd = M.Neighborhood.query.get(name='Projects')

    app_config_id = ObjectId()
    tool_version = {'neighborhood': '0'}
    award = M.Award(app_config_id=app_config_id, tool_version=tool_version)
    award.short = u'Award short'
    award.full = u'Award full'
    award.created_by_neighborhood_id = p_nbhd._id

    project = M.Project.query.get(neighborhood_id=p_nbhd._id, name=u'test')

    award_grant = M.AwardGrant(award=award,
                               granted_by_neighborhood=p_nbhd,
                               granted_to_project=project)

    ThreadLocalORMSession.flush_all()

    with h.push_context(p_nbhd.neighborhood_project._id):
        r = g.markdown_wiki.convert('[[projects]]')
        assert '<div class="feature">Award short</div>' in r, r
        r = g.markdown_wiki.convert('[[projects show_awards_banner=False]]')
        assert '<div class="feature">Award short</div>' not in r, r

def get_project_names(r):
    """
    Extracts a list of project names from a wiki page HTML.
    """
    # projects short names are in h2 elements without any attributes
    # there is one more h2 element, but it has `class` attribute
    #re_proj_names = re.compile('<h2><a[^>]>(.+)<\/a><\/h2>')
    re_proj_names = re.compile('<h2><a[^>]+>(.+)<\/a><\/h2>')
    return [e for e in re_proj_names.findall(r)]

def get_projects_property_in_the_same_order(names, prop):
    """
    Returns a list of projects properties `prop` in the same order as
    project `names`.
    It is required because results of the query are not in the same order as names.
    """
    projects = M.Project.query.find(dict(name={'$in': names})).all()
    projects_dict = dict([(p['name'],p[prop]) for p in projects])
    return [projects_dict[name] for name in names]
