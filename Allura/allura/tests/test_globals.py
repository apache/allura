#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.


import re
import os
from textwrap import dedent
import allura
import unittest
import hashlib
import six
from mock import patch, Mock

from bson import ObjectId
from tg import tmpl_context as c, app_globals as g
import tg
from oembed import OEmbedError

from ming.orm import ThreadLocalORMSession
from alluratest.controller import (
    setup_basic_test,
    setup_global_objects,
    setup_unit_test,
    setup_functional_test,
    setup_trove_categories,
)

from allura import model as M
from allura.lib import helpers as h
from allura.lib.app_globals import ForgeMarkdown
from allura.tests import decorators as td

from forgewiki import model as WM
from forgeblog import model as BM


def setup():
    setup_basic_test()
    setup_unit_test()
    setup_with_tools()


def teardown():
    setup()


@td.with_wiki
def setup_with_tools():
    setup_global_objects()


def squish_spaces(text):
    # \s is whitespace
    # \xa0 is &nbsp; in unicode form
    return re.sub(r'[\s\xa0]+', ' ', text)


def get_project_names(r):
    """
    Extracts a list of project names from a wiki page HTML.
    """
    # projects short names are in h2 elements without any attributes
    # there is one more h2 element, but it has `class` attribute
    # re_proj_names = re.compile(r'<h2><a[^>]>(.+)</a></h2>')
    re_proj_names = re.compile(r'<h2><a[^>]+>(.+)</a></h2>')
    return [e for e in re_proj_names.findall(r)]


def get_projects_property_in_the_same_order(names, prop):
    """
    Returns a list of projects properties `prop` in the same order as
    project `names`.
    It is required because results of the query are not in the same order as names.
    """
    projects = M.Project.query.find(dict(name={'$in': names})).all()
    projects_dict = {p['name']: p[prop] for p in projects}
    return [projects_dict[name] for name in names]


class Test():

    def setup_method(self, method):
        setup()
        p_nbhd = M.Neighborhood.query.get(name='Projects')
        p_test = M.Project.query.get(shortname='test', neighborhood_id=p_nbhd._id)
        self.acl_bak = p_test.acl.copy()

    def teardown_method(self, method):
        user = M.User.by_username('test-admin')
        user.display_name = 'Test Admin'

        p_nbhd = M.Neighborhood.query.get(name='Projects')
        p_test = M.Project.query.get(shortname='test', neighborhood_id=p_nbhd._id)
        p_test.remove_user(M.User.by_username('test-user'))
        p_test.remove_user(M.User.by_username('test-user-0'))
        p_test.acl = self.acl_bak

        ThreadLocalORMSession.flush_all()

    @td.with_wiki
    def test_app_globals(self):
        with h.push_context('test', 'wiki', neighborhood='Projects'):
            assert g.app_static(
                'css/wiki.css') == '/nf/_static_/wiki/css/wiki.css', g.app_static('css/wiki.css')

    def test_macro_projects(self):
        file_name = 'neo-icon-set-454545-256x350.png'
        file_path = os.path.join(
            allura.__path__[0], 'nf', 'allura', 'images', file_name)

        p_nbhd = M.Neighborhood.query.get(name='Projects')
        p_test = M.Project.query.get(shortname='test', neighborhood_id=p_nbhd._id)
        c.project = p_test
        icon_file = open(file_path, 'rb')
        M.ProjectFile.save_image(
            file_name, icon_file, content_type='image/png',
            square=True, thumbnail_size=(48, 48),
            thumbnail_meta=dict(project_id=c.project._id, category='icon'))
        icon_file.close()
        p_test2 = M.Project.query.get(
            shortname='test2', neighborhood_id=p_nbhd._id)
        c.project = p_test2
        icon_file = open(file_path, 'rb')
        M.ProjectFile.save_image(
            file_name, icon_file, content_type='image/png',
            square=True, thumbnail_size=(48, 48),
            thumbnail_meta=dict(project_id=c.project._id, category='icon'))
        icon_file.close()
        p_sub1 = M.Project.query.get(
            shortname='test/sub1', neighborhood_id=p_nbhd._id)
        c.project = p_sub1
        icon_file = open(file_path, 'rb')
        M.ProjectFile.save_image(
            file_name, icon_file, content_type='image/png',
            square=True, thumbnail_size=(48, 48),
            thumbnail_meta=dict(project_id=c.project._id, category='icon'))
        icon_file.close()
        p_test.labels = ['test', 'root']
        p_sub1.labels = ['test', 'sub1']
        # Make one project private
        p_test.private = False
        p_sub1.private = False
        p_test2.private = True

        ThreadLocalORMSession.flush_all()

        with h.push_config(c,
                           project=p_nbhd.neighborhood_project,
                           user=M.User.by_username('test-admin')):
            r = g.markdown_wiki.convert('[[projects]]')
            assert 'alt="Test Project Logo"' in r, r
            assert 'alt="A Subproject Logo"' in r, r
            r = g.markdown_wiki.convert('[[projects labels=root]]')
            assert 'alt="Test Project Logo"' in r, r
            assert 'alt="A Subproject Logo"' not in r, r
            r = g.markdown_wiki.convert('[[projects labels=sub1]]')
            assert 'alt="Test Project Logo"' not in r, r
            assert 'alt="A Subproject Logo"' in r, r
            r = g.markdown_wiki.convert('[[projects labels=test]]')
            assert 'alt="Test Project Logo"' in r, r
            assert 'alt="A Subproject Logo"' in r, r
            r = g.markdown_wiki.convert('[[projects labels=test,root]]')
            assert 'alt="Test Project Logo"' in r, r
            assert 'alt="A Subproject Logo"' not in r, r
            r = g.markdown_wiki.convert('[[projects labels=test,sub1]]')
            assert 'alt="Test Project Logo"' not in r, r
            assert 'alt="A Subproject Logo"' in r, r
            r = g.markdown_wiki.convert('[[projects labels=root|sub1]]')
            assert 'alt="Test Project Logo"' in r, r
            assert 'alt="A Subproject Logo"' in r, r
            r = g.markdown_wiki.convert('[[projects labels=test,root|root,sub1]]')
            assert 'alt="Test Project Logo"' in r, r
            assert 'alt="A Subproject Logo"' not in r, r
            r = g.markdown_wiki.convert('[[projects labels=test,root|test,sub1]]')
            assert 'alt="Test Project Logo"' in r, r
            assert 'alt="A Subproject Logo"' in r, r
            r = g.markdown_wiki.convert('[[projects show_total=True sort=random]]')
            assert '<p class="macro_projects_total">3 Projects' in r, r
            r = g.markdown_wiki.convert(
                '[[projects show_total=True private=True sort=random]]')
            assert '<p class="macro_projects_total">1 Projects' in r, r
            assert 'alt="Test 2 Logo"' in r, r
            assert 'alt="Test Project Logo"' not in r, r
            assert 'alt="A Subproject Logo"' not in r, r

            r = g.markdown_wiki.convert('[[projects show_proj_icon=True]]')
            assert 'alt="Test Project Logo"' in r
            r = g.markdown_wiki.convert('[[projects show_proj_icon=False]]')
            assert 'alt="Test Project Logo"' not in r

    def test_macro_neighborhood_feeds(self):
        p_nbhd = M.Neighborhood.query.get(name='Projects')
        p_test = M.Project.query.get(shortname='test', neighborhood_id=p_nbhd._id)
        with h.push_context('--init--', 'wiki', neighborhood='Projects'):
            r = g.markdown_wiki.convert('[[neighborhood_feeds tool_name=wiki]]')
            assert 'Home modified by' in r, r
            r = re.sub(r'<small>.*? ago</small>', '', r)  # remove "less than 1 second ago" etc
            orig_len = len(r)
            # Make project private & verify we don't see its new feed items
            anon = M.User.anonymous()
            p_test.acl.insert(0, M.ACE.deny(
                M.ProjectRole.anonymous(p_test)._id, 'read'))
            ThreadLocalORMSession.flush_all()
            pg = WM.Page.query.get(title='Home', app_config_id=c.app.config._id)
            pg.text = 'Change'
            with h.push_config(c, user=M.User.by_username('test-admin')):
                pg.commit()
            r = g.markdown_wiki.convert('[[neighborhood_feeds tool_name=wiki]]')
            r = re.sub(r'<small>.*? ago</small>', '', r)  # remove "less than 1 second ago" etc
            new_len = len(r)
            assert new_len == orig_len
            p = BM.BlogPost(title='test me',
                            neighborhood_id=p_test.neighborhood_id)
            p.text = 'test content'
            p.state = 'published'
            p.make_slug()
            with h.push_config(c, user=M.User.by_username('test-admin')):
                p.commit()
            ThreadLocalORMSession.flush_all()
            with h.push_config(c, user=anon):
                r = g.markdown_wiki.convert('[[neighborhood_blog_posts]]')
            assert 'test content' in r

    def test_macro_members(self):
        p_nbhd = M.Neighborhood.query.get(name='Projects')
        p_test = M.Project.query.get(shortname='test', neighborhood_id=p_nbhd._id)
        p_test.add_user(M.User.by_username('test-user'), ['Developer'])
        p_test.add_user(M.User.by_username('test-user-0'), ['Member'])
        ThreadLocalORMSession.flush_all()
        r = g.markdown_wiki.convert('[[members limit=2]]').replace('\t', '').replace('\n', '')
        assert (r ==
                '<div class="markdown_content"><h6>Project Members:</h6>'
                '<ul class="md-users-list">'
                '<li><a href="/u/test-admin/">Test Admin</a> (admin)</li>'
                '<li><a href="/u/test-user/">Test User</a></li>'
                '<li class="md-users-list-more"><a href="/p/test/_members">All Members</a></li>'
                '</ul>'
                '</div>')

    def test_macro_members_escaping(self):
        user = M.User.by_username('test-admin')
        user.display_name = 'Test Admin <script>'
        r = g.markdown_wiki.convert('[[members]]')
        assert (r.replace('\n', '').replace('\t', '') ==
                '<div class="markdown_content"><h6>Project Members:</h6>'
                '<ul class="md-users-list">'
                '<li><a href="/u/test-admin/">Test Admin &lt;script&gt;</a> (admin)</li>'
                '</ul></div>')

    def test_macro_project_admins(self):
        user = M.User.by_username('test-admin')
        user.display_name = 'Test Ådmin <script>'
        with h.push_context('test', neighborhood='Projects'):
            r = g.markdown_wiki.convert('[[project_admins]]')
        assert (r.replace('\n', '') ==
                '<div class="markdown_content"><h6>Project Admins:</h6>'
                '<ul class="md-users-list">'
                '    <li><a href="/u/test-admin/">Test \xc5dmin &lt;script&gt;</a></li>'
                '</ul></div>')

    def test_macro_project_admins_one_br(self):
        p_nbhd = M.Neighborhood.query.get(name='Projects')
        p_test = M.Project.query.get(shortname='test', neighborhood_id=p_nbhd._id)
        p_test.add_user(M.User.by_username('test-user'), ['Admin'])
        ThreadLocalORMSession.flush_all()
        with h.push_config(c, project=p_test):
            r = g.markdown_wiki.convert('[[project_admins]]\n[[download_button]]')

        assert '</a><br/><br/><a href=' not in r, r
        assert '</a></li><li><a href=' in r, r

    def test_macro_include_no_extra_br(self):
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

        expected_html = '''<div class="markdown_content"><p></p><div>
    <div class="markdown_content"><p>included page 1</p></div>
    </div>
    <div>
    <div class="markdown_content"><p>included page 2</p></div>
    </div>
    <div>
    <div class="markdown_content"><p>included page 3</p></div>
    </div>
    <p></p></div>'''
        assert squish_spaces(html) == squish_spaces(expected_html)

    @td.with_tool('test', 'Wiki', 'wiki2')
    def test_macro_include_permissions(self):
        p_nbhd = M.Neighborhood.query.get(name='Projects')
        p_test = M.Project.query.get(shortname='test', neighborhood_id=p_nbhd._id)
        wiki = p_test.app_instance('wiki')
        wiki2 = p_test.app_instance('wiki2')
        with h.push_context(p_test._id, app_config_id=wiki.config._id):
            p = WM.Page.upsert(title='CanRead')
            p.text = 'Can see this!'
            p.commit()
            ThreadLocalORMSession.flush_all()

        with h.push_context(p_test._id, app_config_id=wiki2.config._id):
            role = M.ProjectRole.by_name('*anonymous')._id
            read_perm = M.ACE.allow(role, 'read')
            acl = c.app.config.acl
            if read_perm in acl:
                acl.remove(read_perm)
            p = WM.Page.upsert(title='CanNotRead')
            p.text = 'Can not see this!'
            p.commit()
            ThreadLocalORMSession.flush_all()

        with h.push_context(p_test._id, app_config_id=wiki.config._id):
            c.user = M.User.anonymous()
            md = '[[include ref=CanRead]]\n[[include ref=wiki2:CanNotRead]]'
            html = g.markdown_wiki.convert(md)
            assert 'Can see this!' in html
            assert 'Can not see this!' not in html
            assert "[[include: you don't have a read permission for wiki2:CanNotRead]]" in html

    @patch('oembed.OEmbedEndpoint.fetch')
    def test_macro_embed(self, oembed_fetch):
        oembed_fetch.return_value = {
            "html": '<iframe width="480" height="270" src="http://www.youtube.com/embed/kOLpSPEA72U?feature=oembed" '
                    'frameborder="0" allowfullscreen></iframe>)',
            "title": "Nature's 3D Printer: MIND BLOWING Cocoon in Rainforest - Smarter Every Day 94",
        }
        r = g.markdown_wiki.convert('[[embed url=http://www.youtube.com/watch?v=kOLpSPEA72U]]')
        assert ('<p><iframe height="270" '
                'src="https://www.youtube-nocookie.com/embed/kOLpSPEA72U?feature=oembed" width="480"></iframe></p>' in
                r.replace('\n', ''))

    def test_macro_embed_video_gone(self):
        # this does a real fetch
        r = g.markdown_wiki.convert('[[embed url=https://www.youtube.com/watch?v=OWsFqPZ3v-0]]')
        r = str(r)  # convert away from Markup, to get better assertion diff output
        # either of these could happen depending on the mood of youtube's oembed API:
        assert r in [
            '<div class="markdown_content"><p>Video not available</p></div>',
            '<div class="markdown_content"><p>Could not embed: https://www.youtube.com/watch?v=OWsFqPZ3v-0</p></div>',
        ]

    @patch('oembed.OEmbedEndpoint.fetch')
    def test_macro_embed_video_error(self, oembed_fetch):
        oembed_fetch.side_effect = OEmbedError('Invalid mime-type in response...')
        r = g.markdown_wiki.convert('[[embed url=http://www.youtube.com/watch?v=6YbBmqUnoQM]]')
        assert (r == '<div class="markdown_content"><p>Could not embed: '
                'http://www.youtube.com/watch?v=6YbBmqUnoQM</p></div>')

    def test_macro_embed_notsupported(self):
        r = g.markdown_wiki.convert('[[embed url=http://vimeo.com/46163090]]')
        assert (
            r == '<div class="markdown_content"><p>[[embed url=http://vimeo.com/46163090]]</p></div>')

    def test_markdown_toc(self):
        with h.push_context('test', neighborhood='Projects'):
            r = g.markdown_wiki.convert(dedent("""\
                [TOC]

                # Header 1

                ## Header 2"""))
        assert dedent('''\
            <ul>
            <li><a href="#header-1">Header 1</a><ul>
            <li><a href="#header-2">Header 2</a></li>
            </ul>
            </li>
            </ul>''') in r

    def test_wiki_artifact_links(self):
        text = g.markdown.convert('See [18:13:49]')
        assert 'See <span>[18:13:49]</span>' in text, text
        with h.push_context('test', 'wiki', neighborhood='Projects'):
            text = g.markdown.convert('Read [here](Home) about our project')
            assert '<a class="" href="/p/test/wiki/Home/">here</a>' in text, text
            text = g.markdown.convert('[Go home](test:wiki:Home)')
            assert '<a class="" href="/p/test/wiki/Home/">Go home</a>' in text, text
            text = g.markdown.convert('See [test:wiki:Home]')
            assert '<a class="alink" href="/p/test/wiki/Home/">[test:wiki:Home]</a>' in text, text

    def test_markdown_links(self):
        with patch.dict(tg.config, {'nofollow_exempt_domains': 'foobar.net'}):
            text = g.markdown.convert('Read [here](http://foobar.net/) about our project')
            assert 'class="" href="http://foobar.net/">here</a> about' in text

        text = g.markdown.convert('Read [here](http://foobar.net/) about our project')
        assert 'class="" href="http://foobar.net/" rel="nofollow">here</a> about' in text

        text = g.markdown.convert('Read [here](/p/foobar/blah) about our project')
        assert 'class="" href="/p/foobar/blah">here</a> about' in text

        text = g.markdown.convert('Read [here](/p/foobar/blah/) about our project')
        assert 'class="" href="/p/foobar/blah/">here</a> about' in text

        text = g.markdown.convert('Read <http://foobar.net/> about our project')
        assert 'href="http://foobar.net/" rel="nofollow">http://foobar.net/</a> about' in text

    def test_markdown_and_html(self):
        with h.push_context('test', neighborhood='Projects'):
            r = g.markdown_wiki.convert('<div style="float:left">blah</div>')
        assert '<div style="float: left;">blah</div>' in r, r

    def test_markdown_within_html(self):
        with h.push_context('test', neighborhood='Projects'):
            r = g.markdown_wiki.convert('<div style="float:left" markdown>**blah**</div>')
        assert ('<div style="float: left;"><p><strong>blah</strong></p></div>' in
                r.replace('\n', ''))

    def test_markdown_with_html_comments(self):
        text = g.markdown.convert('test <!-- comment -->')
        assert '<div class="markdown_content"><p>test </p></div>' == text, text

    def test_markdown_big_text(self):
        '''If text is too big g.markdown.convert should return plain text'''
        text = 'a' * 40001
        assert g.markdown.convert(text) == '<pre>%s</pre>' % text
        assert g.markdown_wiki.convert(text) == '<pre>%s</pre>' % text

    def test_markdown_basics(self):
        with h.push_context('test', 'wiki', neighborhood='Projects'):
            text = g.markdown.convert('# Foo!\n[Home]')
            assert (text ==
                    '<div class="markdown_content"><h1 id="foo">Foo!</h1>\n'
                    '<p><a class="alink" href="/p/test/wiki/Home/">[Home]</a></p></div>')
            text = g.markdown.convert('# Foo!\n[Rooted]')
            assert (text ==
                    '<div class="markdown_content"><h1 id="foo">Foo!</h1>\n'
                    '<p><span>[Rooted]</span></p></div>')

        assert (
            g.markdown.convert('Multi\nLine') ==
            '<div class="markdown_content"><p>Multi<br/>\n'
            'Line</p></div>')
        assert (
            g.markdown.convert('Multi\n\nLine') ==
            '<div class="markdown_content"><p>Multi</p>\n'
            '<p>Line</p></div>')

        # should not raise an exception:
        assert g.markdown.convert("<class 'foo'>") == \
            '''<div class="markdown_content"><p>&lt;class 'foo'=""&gt;&lt;/class&gt;</p></div>'''

        assert g.markdown.convert(dedent('''\
            # Header

            Some text in a regular paragraph

                :::python
                for i in range(10):
                    print i
            ''')) == dedent('''\
                <div class="markdown_content"><h1 id="header">Header</h1>
                <p>Some text in a regular paragraph</p>
                <div class="codehilite"><pre><span></span><code><span class="k">for</span> <span class="n">i</span> <span class="ow">in</span> <span class="nb">range</span><span class="p">(</span><span class="mi">10</span><span class="p">):</span>
                    <span class="nb">print</span> <span class="n">i</span>
                </code></pre></div>
                </div>''')
        assert (
            g.forge_markdown(email=True).convert('[Home]') ==
            # uses localhost:
            '<div class="markdown_content"><p><a class="alink" href="http://localhost/p/test/wiki/Home/">[Home]</a></p></div>')
        assert g.markdown.convert(dedent('''\
            ~~~~
            def foo(): pass
            ~~~~''')) == dedent('''\
                <div class="markdown_content"><div class="codehilite"><pre><span></span><code>def foo(): pass
                </code></pre></div>
                </div>''')

    def test_markdown_list_without_break(self):
        # this is not a valid way to make a list in original Markdown or python-markdown
        #   https://github.com/Python-Markdown/markdown/issues/874
        # it is valid in the CommonMark spec https://spec.commonmark.org/0.30/#lists
        # TODO: try https://github.com/adamb70/mdx-breakless-lists
        #       or https://gitlab.com/ayblaq/prependnewline
        assert (
            g.markdown.convert(dedent('''\
    Regular text
    * first item
    * second item''')) ==
            '<div class="markdown_content"><p>Regular text\n'  # no <br>
            '* first item\n'  # no <br>
            '* second item</p></div>')

        assert (
            g.markdown.convert(dedent('''\
    Regular text
    - first item
    - second item''')) ==
            '<div class="markdown_content"><p>Regular text<br/>\n'
            '- first item<br/>\n'
            '- second item</p></div>')

        assert (
            g.markdown.convert(dedent('''\
    Regular text
    + first item
    + second item''')) ==
            '<div class="markdown_content"><p>Regular text<br/>\n'
            '+ first item<br/>\n'
            '+ second item</p></div>')

        assert (
            g.markdown.convert(dedent('''\
    Regular text
    1. first item
    2. second item''')) ==
            '<div class="markdown_content"><p>Regular text<br/>\n'
            '1. first item<br/>\n'
            '2. second item</p></div>')

    def test_markdown_autolink(self):
        tgt = 'http://everything2.com/?node=nate+oostendorp'
        s = g.markdown.convert('This is %s' % tgt)
        assert (
            s == f'<div class="markdown_content"><p>This is <a href="{tgt}" rel="nofollow">{tgt}</a></p></div>')
        assert '<a href=' in g.markdown.convert('This is http://domain.net')
        # beginning of doc
        assert '<a href=' in g.markdown.convert('http://domain.net abc')
        # beginning of a line
        assert ('<br/>\n<a href="http://' in
                g.markdown.convert('foobar\nhttp://domain.net abc'))
        # no conversion of these urls:
        assert ('a blahttp://sdf.com z' in
                g.markdown.convert('a blahttp://sdf.com z'))
        assert ('literal <code>http://domain.net</code> literal' in
                g.markdown.convert('literal `http://domain.net` literal'))
        assert ('<pre><span></span><code>preformatted http://domain.net\n</code></pre>' in
                g.markdown.convert('    :::text\n'
                                   '    preformatted http://domain.net'))

    def test_markdown_autolink_with_escape(self):
        # \_ is unnecessary but valid markdown escaping and should be considered as a regular underscore
        # (it occurs during html2text conversion during project migrations)
        r = g.markdown.convert(r'a http://www.phpmyadmin.net/home\_page/security/\#target b')
        assert 'href="http://www.phpmyadmin.net/home_page/security/#target"' in r, r

    def test_markdown_invalid_script(self):
        r = g.markdown.convert('<script>alert(document.cookies)</script>')
        assert '<div class="markdown_content">&lt;script&gt;alert(document.cookies)&lt;/script&gt;\n</div>' == r

    def test_markdown_invalid_onerror(self):
        r = g.markdown.convert('<img src=x onerror=alert(document.cookie)>')
        assert 'onerror' not in r

    def test_markdown_invalid_tagslash(self):
        r = g.markdown.convert('<div/onload><img src=x onerror=alert(document.cookie)>')
        assert 'onerror' not in r

    def test_markdown_invalid_script_in_link(self):
        r = g.markdown.convert('[xss](http://"><a onmouseover=prompt(document.domain)>xss</a>)')
        assert ('<div class="markdown_content"><p><a class="" '
                '''href='http://"&gt;&lt;a%20onmouseover=prompt(document.domain)&gt;xss&lt;/a&gt;' '''
                'rel="nofollow">xss</a></p></div>' == r)

    def test_markdown_invalid_script_in_link2(self):
        r = g.markdown.convert('[xss](http://"><img src=x onerror=alert(document.cookie)>)')
        assert ('<div class="markdown_content"><p><a class="" '
                '''href='http://"&gt;&lt;img%20src=x%20onerror=alert(document.cookie)&gt;' '''
                'rel="nofollow">xss</a></p></div>' == r)

    def test_markdown_extremely_slow(self):
        r = g.markdown.convert('''bonjour, voila ce que j'obtient en voulant ajouter un utilisateur a un groupe de sécurite, que ce soit sur un groupe pre-existant, ou sur un groupe crée.
    message d'erreur:

    ERROR: Could not complete the Add UserLogin To SecurityGroup [file:/C:/neogia/ofbizNeogia/applications/securityext/script/org/ofbiz/securityext/securitygroup/SecurityGroupServices.xml#addUserLoginToSecurityGroup] process [problem creating the newEntity value: Exception while inserting the following entity: [GenericEntity:UserLoginSecurityGroup][createdStamp,2006-01-23 17:42:39.312(java.sql.Timestamp)][createdTxStamp,2006-01-23 17:42:38.875(java.sql.Timestamp)][fromDate,2006-01-23 17:42:39.312(java.sql.Timestamp)][groupId,FULLADMIN(java.lang.String)][lastUpdatedStamp,2006-01-23 17:42:39.312(java.sql.Timestamp)][lastUpdatedTxStamp,2006-01-23 17:42:38.875(java.sql.Timestamp)][thruDate,null()][userLoginId,10012(java.lang.String)] (while inserting: [GenericEntity:UserLoginSecurityGroup][createdStamp,2006-01-23 17:42:39.312(java.sql.Timestamp)][createdTxStamp,2006-01-23 17:42:38.875(java.sql.Timestamp)][fromDate,2006-01-23 17:42:39.312(java.sql.Timestamp)][groupId,FULLADMIN(java.lang.String)][lastUpdatedStamp,2006-01-23 17:42:39.312(java.sql.Timestamp)][lastUpdatedTxStamp,2006-01-23 17:42:38.875(java.sql.Timestamp)][thruDate,null()][userLoginId,10012(java.lang.String)] (SQL Exception while executing the following:INSERT INTO public.USER_LOGIN_SECURITY_GROUP (USER_LOGIN_ID, GROUP_ID, FROM_DATE, THRU_DATE, LAST_UPDATED_STAMP, LAST_UPDATED_TX_STAMP, CREATED_STAMP, CREATED_TX_STAMP) VALUES (?, ?, ?, ?, ?, ?, ?, ?) (ERROR: insert or update on table &quot;user_login_security_group&quot; violates foreign key constraint &quot;user_secgrp_user&quot;)))].

    à priori les données du formulaire ne sont pas traitées : VALUES (?, ?, ?, ?, ?, ?, ?, ?) ce qui entraine l'echec du traitement SQL.


    Si une idée vous vient à l'esprit, merci de me tenir au courant.

    cordialement, julien.''')
        assert True   # finished!

    @td.with_tool('test', 'Wiki', 'wiki-len')
    def test_markdown_link_length_limits(self):
        with h.push_context('test', 'wiki-len', neighborhood='Projects'):
            # these are always ok, no matter the NOBRACKET length
            WM.Page.upsert(title='12345678901').commit()
            text = g.markdown.convert('See [12345678901]')
            assert 'href="/p/test/wiki-len/12345678901/">[12345678901]</a>' in text, text
            WM.Page.upsert(title='this is 26 characters long').commit()
            text = g.markdown.convert('See [this is 26 characters long]')
            assert 'href="/p/test/wiki-len/this%20is%2026%20characters%20long/">[this is 26 characters long]</a>' in text, text

            # NOBRACKET regex length impacts standard markdown links
            text = g.markdown.convert('See [short](http://a.de)')
            assert 'href="http://a.de" rel="nofollow">short</a>' in text, text
            text = g.markdown.convert('See [this is 26 characters long](http://a.de)')
            assert 'href="http://a.de" rel="nofollow">this is 26 characters long</a>' in text, text  # {0,12} fails {0,13} ok

            # NOBRACKET regex length impacts our custom artifact links
            text = g.markdown.convert('See [short](Home)')
            assert 'href="/p/test/wiki-len/Home/">short</a>' in text, text
            text = g.markdown.convert('See [123456789](Home)')
            assert 'href="/p/test/wiki-len/Home/">123456789</a>' in text, text
            text = g.markdown.convert('See [12345678901](Home)')
            assert 'href="/p/test/wiki-len/Home/">12345678901</a>' in text, text  # {0,5} fails, {0,6} ok
            text = g.markdown.convert('See [this is 16 chars](Home)')
            assert 'href="/p/test/wiki-len/Home/">this is 16 chars</a>' in text, text  # {0,7} fails {0,8} ok
            text = g.markdown.convert('See [this is 26 characters long](Home)')
            assert 'href="/p/test/wiki-len/Home/">this is 26 characters long</a>' in text, text  # {0,12} fails {0,13} ok

            # limit, currently
            charSuperLong = '1234567890'*21
            text = g.markdown.convert(f'See [{charSuperLong}](Home)')
            assert f'<span>[{charSuperLong}]</span>(Home)' in text, text  # current limitation, not a link
            # assert f'href="/p/test/wiki-len/Home/">{charSuperLong}</a>' in text, text  # ideal output

    def test_macro_include(self):
        r = g.markdown.convert('[[include ref=Home id=foo]]')
        assert '<div id="foo">' in r, r
        assert 'href="../foo"' in g.markdown.convert('[My foo](foo)')
        assert 'href="..' not in g.markdown.convert('[My foo](./foo)')

    def test_macro_nbhd_feeds(self):
        with h.push_context('--init--', 'wiki', neighborhood='Projects'):
            r = g.markdown_wiki.convert('[[neighborhood_feeds tool_name=wiki]]')
            assert 'Home modified by ' in r, r
            assert '&lt;div class="markdown_content"&gt;' not in r

    def test_sort_alpha(self):
        p_nbhd = M.Neighborhood.query.get(name='Projects')

        with h.push_context(p_nbhd.neighborhood_project._id):
            r = g.markdown_wiki.convert('[[projects sort=alpha]]')
            project_list = get_project_names(r)
            assert project_list == sorted(project_list)

    def test_sort_registered(self):
        p_nbhd = M.Neighborhood.query.get(name='Projects')

        with h.push_context(p_nbhd.neighborhood_project._id):
            r = g.markdown_wiki.convert('[[projects sort=last_registered]]')
            project_names = get_project_names(r)
            ids = get_projects_property_in_the_same_order(project_names, '_id')
            assert ids == sorted(ids, reverse=True)

    def test_sort_updated(self):
        p_nbhd = M.Neighborhood.query.get(name='Projects')

        with h.push_context(p_nbhd.neighborhood_project._id):
            r = g.markdown_wiki.convert('[[projects sort=last_updated]]')
            project_names = get_project_names(r)
            updated_at = get_projects_property_in_the_same_order(
                project_names, 'last_updated')
            assert updated_at == sorted(updated_at, reverse=True)

    def test_filtering(self):
        # set up for test
        from random import choice
        setup_trove_categories()
        random_trove = choice(M.TroveCategory.query.find().all())
        test_project = M.Project.query.get(shortname='test')
        test_project_troves = getattr(test_project, 'trove_' + random_trove.type)
        test_project_troves.append(random_trove._id)
        ThreadLocalORMSession.flush_all()

        p_nbhd = M.Neighborhood.query.get(name='Projects')
        with h.push_config(c,
                           project=p_nbhd.neighborhood_project,
                           user=M.User.by_username('test-admin')):
            r = g.markdown_wiki.convert(
                '[[projects category="%s"]]' % random_trove.fullpath)
            project_names = get_project_names(r)
            assert [test_project.name] == project_names

    def test_projects_macro(self):
        two_column_style = 'width: 330px;'

        p_nbhd = M.Neighborhood.query.get(name='Projects')
        with h.push_config(c,
                           project=p_nbhd.neighborhood_project,
                           user=M.User.anonymous()):
            # test columns
            r = g.markdown_wiki.convert('[[projects display_mode=list columns=2]]')
            assert two_column_style in r
            r = g.markdown_wiki.convert('[[projects display_mode=list columns=3]]')
            assert two_column_style not in r

    @td.with_user_project('test-admin')
    @td.with_user_project('test-user-1')
    def test_myprojects_macro(self):
        h.set_context('u/%s' % (c.user.username), 'wiki', neighborhood='Users')
        r = g.markdown_wiki.convert('[[my_projects]]')
        for p in c.user.my_projects():
            if p.deleted or p.is_nbhd_project:
                continue
            proj_title = f'<h2><a href="{p.url()}">{p.name}</a></h2>'
            assert proj_title in r

        h.set_context('u/test-user-1', 'wiki', neighborhood='Users')
        user = M.User.query.get(username='test-user-1')
        r = g.markdown_wiki.convert('[[my_projects]]')
        for p in user.my_projects():
            if p.deleted or p.is_nbhd_project:
                continue
            proj_title = f'<h2><a href="{p.url()}">{p.name}</a></h2>'
            assert proj_title in r

    def test_hideawards_macro(self):
        p_nbhd = M.Neighborhood.query.get(name='Projects')

        app_config_id = ObjectId()
        award = M.Award(app_config_id=app_config_id)
        award.short = 'Award short'
        award.full = 'Award full'
        award.created_by_neighborhood_id = p_nbhd._id

        project = M.Project.query.get(
            neighborhood_id=p_nbhd._id, shortname='test')

        M.AwardGrant(
            award=award,
            award_url='http://award.org',
            comment='Winner!',
            granted_by_neighborhood=p_nbhd,
            granted_to_project=project)

        ThreadLocalORMSession.flush_all()

        with h.push_context(p_nbhd.neighborhood_project._id):
            r = g.markdown_wiki.convert('[[projects]]')
            assert ('<div class="feature"> <a href="http://award.org" rel="nofollow" title="Winner!">'
                    'Award short</a> </div>' in
                    squish_spaces(r))

            r = g.markdown_wiki.convert('[[projects show_awards_banner=False]]')
            assert 'Award short' not in r

    @td.with_tool('test', 'Blog', 'blog')
    def test_project_blog_posts_macro(self):
        from forgeblog import model as BM
        with h.push_context('test', 'blog', neighborhood='Projects'):
            BM.BlogPost.new(
                title='Test title',
                text='test post',
                state='published',
            )
            BM.BlogPost.new(
                title='Test title2',
                text='test post2',
                state='published',
            )

            r = g.markdown_wiki.convert('[[project_blog_posts]]')
            assert 'Test title</a></h3>' in r
            assert 'Test title2</a></h3>' in r
            assert '<div class="markdown_content"><p>test post</p></div>' in r
            assert '<div class="markdown_content"><p>test post2</p></div>' in r
            assert 'by <em>Test Admin</em>' in r

    def test_project_screenshots_macro(self):
        with h.push_context('test', neighborhood='Projects'):
            M.ProjectFile(project_id=c.project._id, category='screenshot', caption='caption', filename='test_file.jpg')
            ThreadLocalORMSession.flush_all()

            r = g.markdown_wiki.convert('[[project_screenshots]]')

            assert 'href="/p/test/screenshot/test_file.jpg"' in r
            assert 'src="/p/test/screenshot/test_file.jpg/thumb"' in r


class TestCachedMarkdown(unittest.TestCase):

    def setup_method(self, method):
        self.md = ForgeMarkdown()
        self.post = M.Post()
        self.post.text = '**bold**'
        self.expected_html = '<p><strong>bold</strong></p>'

    def test_bad_source_field_name(self):
        self.assertRaises(AttributeError, self.md.cached_convert,
                          self.post, 'no_such_field')

    def test_missing_cache_field(self):
        delattr(self.post, 'text_cache')
        html = self.md.cached_convert(self.post, 'text')
        self.assertEqual(html, self.expected_html)

    @patch.dict('allura.lib.app_globals.config', markdown_cache_threshold='-0.01')
    def test_non_ascii(self):
        self.post.text = 'å∫ç'
        expected = '<p>å∫ç</p>'
        # test with empty cache
        self.assertEqual(expected, self.md.cached_convert(self.post, 'text'))
        # test with primed cache
        self.assertEqual(expected, self.md.cached_convert(self.post, 'text'))

    @patch.dict('allura.lib.app_globals.config', markdown_cache_threshold='-0.01')
    def test_empty_cache(self):
        html = self.md.cached_convert(self.post, 'text')
        self.assertEqual(html, self.expected_html)
        self.assertEqual(html, self.post.text_cache.html)
        self.assertEqual(hashlib.md5(self.post.text.encode('utf-8')).hexdigest(),
                         self.post.text_cache.md5)
        self.assertTrue(self.post.text_cache.render_time > 0)

    @patch.dict('allura.lib.app_globals.config', markdown_cache_threshold='-0.01')
    def test_stale_cache(self):
        old = self.md.cached_convert(self.post, 'text')
        self.post.text = 'new, different source text'
        html = self.md.cached_convert(self.post, 'text')
        self.assertNotEqual(old, html)
        self.assertEqual(html, self.post.text_cache.html)
        self.assertEqual(hashlib.md5(self.post.text.encode('utf-8')).hexdigest(),
                         self.post.text_cache.md5)
        self.assertTrue(self.post.text_cache.render_time > 0)

    @patch.dict('allura.lib.app_globals.config', markdown_cache_threshold='-0.01')
    def test_valid_cache(self):
        from markupsafe import Markup
        self.md.cached_convert(self.post, 'text')
        with patch.object(self.md, 'convert') as convert_func:
            html = self.md.cached_convert(self.post, 'text')
            self.assertEqual(html, self.expected_html)
            self.assertIsInstance(html, Markup)
            self.assertFalse(convert_func.called)
            self.post.text = "text [[include]] pass"
            html = self.md.cached_convert(self.post, 'text')
            self.assertTrue(convert_func.called)

    @patch.dict('allura.lib.app_globals.config', markdown_cache_threshold='-0.01')
    def test_cacheable_macro(self):
        # cachable
        self.post.text = "text [[img src=...]] pass"
        del self.post.text_cache
        self.md.cached_convert(self.post, 'text')
        assert self.post.text_cache.html

        # cachable, its not even a macro!
        self.post.text = "text [[ blah"
        del self.post.text_cache
        self.md.cached_convert(self.post, 'text')
        assert self.post.text_cache.html

        # not cacheable
        self.post.text = "text [[include file=...]] pass"
        del self.post.text_cache
        self.md.cached_convert(self.post, 'text')
        assert not self.post.text_cache.html

        # not cacheable
        self.post.text = "text [[   \n   include file=... ]] pass"
        del self.post.text_cache
        self.md.cached_convert(self.post, 'text')
        assert not self.post.text_cache.html

    @patch.dict('allura.lib.app_globals.config', {})
    def test_no_threshold_defined(self):
        html = self.md.cached_convert(self.post, 'text')
        self.assertEqual(html, self.expected_html)
        self.assertIsNone(self.post.text_cache.md5)
        self.assertIsNone(self.post.text_cache.html)
        self.assertIsNone(self.post.text_cache.render_time)

    @patch.dict('allura.lib.app_globals.config', markdown_cache_threshold='foo')
    def test_invalid_threshold(self):
        html = self.md.cached_convert(self.post, 'text')
        self.assertEqual(html, self.expected_html)
        self.assertIsNone(self.post.text_cache.md5)
        self.assertIsNone(self.post.text_cache.html)
        self.assertIsNone(self.post.text_cache.render_time)

    @patch.dict('allura.lib.app_globals.config', markdown_cache_threshold='99999')
    def test_render_time_below_threshold(self):
        html = self.md.cached_convert(self.post, 'text')
        self.assertEqual(html, self.expected_html)
        self.assertIsNone(self.post.text_cache.md5)
        self.assertIsNone(self.post.text_cache.html)
        self.assertIsNone(self.post.text_cache.render_time)

    @patch.dict('allura.lib.app_globals.config', {})
    def test_all_expected_keys_exist_in_cache(self):
        self.md.cached_convert(self.post, 'text')
        required_keys = ['fix7528', 'html', 'md5', 'render_time']
        keys = sorted(self.post.text_cache.keys())
        self.assertEqual(required_keys, keys)


class TestEmojis(unittest.TestCase):

    def test_markdown_emoji_atomic(self):
        output = g.markdown.convert(':smile:')
        assert '<p>\U0001F604</p>' in output
        output = g.markdown.convert(':+1:')
        assert '<p>\U0001F44D</p>' in output
        output = g.markdown.convert(':Bosnia_&_Herzegovina:')
        assert '<p>\U0001F1E7\U0001F1E6</p>' in output
        output = g.markdown.convert(':Åland_Islands:')  # emoji code with non-ascii character
        assert '<p>\U0001F1E6\U0001F1FD</p>' in output

    def test_markdown_emoji_with_text(self):
        output = g.markdown.convert('Thumbs up emoji :+1: wow!')
        assert '<p>Thumbs up emoji \U0001F44D wow!</p>' in output
        output = g.markdown.convert('More emojis :+1::camel::three_o’clock: wow!')
        assert '<p>More emojis \U0001F44D\U0001F42B\U0001F552 wow!</p>' in output
        output = g.markdown.convert(':man_bouncing_ball_medium-light_skin_tone:emoji:+1:')
        assert '<p>\U000026F9\U0001F3FC\U0000200D\U00002642\U0000FE0Femoji\U0001F44D</p>' in output

    def test_markdown_emoji_in_code(self):
        output = g.markdown.convert('This will not become an emoji `:+1:`')
        assert '<p>This will not become an emoji <code>:+1:</code></p>' in output
        output = g.markdown.convert('```html\n<p>:camel:</p>\n```')
        assert ':camel:' in output
        output = g.markdown.convert('~~~\n:camel:\n~~~')
        assert '<pre><span></span><code>:camel:\n</code></pre>' in output

    def test_markdown_commit_with_emojis(self):
        output = g.markdown_commit.convert('Thumbs up emoji :+1: wow!')
        assert 'Thumbs up emoji \U0001F44D wow!' in output
        output = g.markdown.convert('More emojis :+1::camel::three_o’clock: wow!')
        assert 'More emojis \U0001F44D\U0001F42B\U0001F552 wow!' in output


class TestUserMentions(unittest.TestCase):

    def test_markdown_user_mention_default(self):
        output = g.markdown.convert('Hello.. @nouser1, how are you?')
        assert 'Hello.. @nouser1, how are you?' in output
        u1 = M.User.register(dict(username='admin1'), make_project=True)
        ThreadLocalORMSession.flush_all()
        output = g.markdown.convert('Hello.. @admin1, how are you?')
        assert 'class="user-mention"' in output
        assert ('href="%s"' % u1.url()) in output
        u2 = M.User.register(dict(username='admin-2'), make_project=True)
        ThreadLocalORMSession.flush_all()
        output = g.markdown.convert('Do you know @ab? @admin-2 has solved it!')
        assert 'Do you know @ab?' in output
        assert 'class="user-mention"' in output
        assert ('href="%s"' % u2.url()) in output
        output = g.markdown.convert('test@admin1.com Hey!')
        assert 'test@admin1.com Hey!' in output

    def test_markdown_user_mention_in_code(self):
        u1 = M.User.register(dict(username='admin-user-4'), make_project=True)
        ThreadLocalORMSession.flush_all()
        output = g.markdown.convert('Hello.. `@admin-user-4, how` are you?')
        assert 'class="user-mention"' not in output
        assert '<code>' in output
        assert ('href="%s"' % u1.url()) not in output
        output = g.markdown.convert('Hello.. This is code \n~~~python\nprint("@admin-user-4")\n~~~')
        assert 'class="user-mention"' not in output
        assert '<div class="codehilite">' in output
        assert ('href="%s"' % u1.url()) not in output

    @patch('allura.lib.widgets.forms.NeighborhoodProjectShortNameValidator')
    def test_markdown_user_mention_underscores(self, NeighborhoodProjectShortNameValidator):
        username = 'r_808__'
        NeighborhoodProjectShortNameValidator.to_python.return_value = username
        u1 = M.User.register(dict(username=username), make_project=True)
        ThreadLocalORMSession.flush_all()
        output = g.markdown.convert(f'Hello.. @{username}, how are you?')
        assert 'class="user-mention"' in output


class TestHandlePaging(unittest.TestCase):

    def setup_method(self, method):
        prefs = {}
        c.user = Mock()

        def get_pref(name):
            return prefs.get(name)

        def set_pref(name, value):
            prefs[name] = value
        c.user.get_pref = get_pref
        c.user.set_pref = set_pref

    def test_with_limit(self):
        self.assertEqual(g.handle_paging(10, 0), (10, 0, 0))
        self.assertEqual(g.handle_paging(10, 2), (10, 2, 20))
        # handle paging must not mess up user preferences
        self.assertEqual(c.user.get_pref('results_per_page'), None)
        # maximum enforced
        self.assertEqual(g.handle_paging(99999999, 0), (500, 0, 0))

    def test_without_limit(self):
        # default limit = 25
        self.assertEqual(g.handle_paging(None, 0), (25, 0, 0))
        self.assertEqual(g.handle_paging(None, 2), (25, 2, 50))
        # handle paging must not mess up user preferences
        self.assertEqual(c.user.get_pref('results_per_page'), None)

        # user has page size preference
        c.user.set_pref('results_per_page', 100)
        self.assertEqual(g.handle_paging(None, 0), (100, 0, 0))
        self.assertEqual(g.handle_paging(None, 2), (100, 2, 200))
        # handle paging must not mess up user preferences
        self.assertEqual(c.user.get_pref('results_per_page'), 100)

    def test_without_limit_with_default(self):
        # default limit is not used when explicitly provided
        self.assertEqual(g.handle_paging(None, 0, 30), (30, 0, 0))
        self.assertEqual(g.handle_paging(None, 2, 30), (30, 2, 60))
        # handle paging must not mess up user preferences
        self.assertEqual(c.user.get_pref('results_per_page'), None)

        # user has page size preference, which is not affected by default
        c.user.set_pref('results_per_page', 25)
        self.assertEqual(g.handle_paging(None, 0, 30), (25, 0, 0))
        self.assertEqual(g.handle_paging(None, 2, 30), (25, 2, 50))
        # handle paging must not mess up user preferences
        self.assertEqual(c.user.get_pref('results_per_page'), 25)

    def test_with_invalid_limit(self):
        self.assertEqual(g.handle_paging('foo', 0, 30), (30, 0, 0))

        c.user.set_pref('results_per_page', 'bar')
        self.assertEqual(g.handle_paging(None, 0, 30), (30, 0, 0))

    def test_with_invalid_page(self):
        self.assertEqual(g.handle_paging(10, 'asdf', 30), (10, 0, 0))


class TestIconRender:

    def setup_method(self, method):
        self.i = g.icons['edit']

    def test_default(self):
        html = '<a class="icon" href="#" title="Edit"><i class="fa fa-edit"></i></a>'
        assert html == self.i.render()

    def test_show_title(self):
        html = '<a class="icon" href="#" title="Edit"><i class="fa fa-edit"></i>&nbsp;Edit</a>'
        assert html == self.i.render(show_title=True)

        html = '<a class="icon" href="#" title="&lt;script&gt;"><i class="fa fa-edit"></i>&nbsp;&lt;script&gt;</a>'
        assert html == self.i.render(show_title=True, title="<script>")

    def test_extra_css(self):
        html = '<a class="icon reply btn" href="#" title="Edit"><i class="fa fa-edit"></i></a>'
        assert html == self.i.render(extra_css='reply btn')

    def test_no_closing_tag(self):
        html = '<a class="icon" href="#" title="Edit"><i class="fa fa-edit"></i>'
        assert html == self.i.render(closing_tag=False)

    def test_tag(self):
        html = '<div class="icon" title="Edit"><i class="fa fa-edit"></i></div>'
        assert html == self.i.render(tag='div')

    def test_kwargs(self):
        html = '<a class="icon" data-id="123" href="#" title="Edit"><i class="fa fa-edit"></i></a>'
        assert html == self.i.render(**{'data-id': '123'})

    def test_escaping(self):
        html = '<a class="icon &#34;" data-url="&gt;" href="#" title="Edit"><i class="fa fa-edit"></i></a>'
        assert html == self.i.render(extra_css='"', **{'data-url': '>'})
