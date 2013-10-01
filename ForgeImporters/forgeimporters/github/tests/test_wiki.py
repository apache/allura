# coding: utf-8

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

from unittest import TestCase
from nose.tools import assert_equal
from mock import Mock, patch, call

from IPython.testing.decorators import module_not_available, skipif
from allura.tests import TestController
from allura.tests.decorators import with_tool, without_module
from alluratest.controller import setup_basic_test
from forgeimporters.github.wiki import GitHubWikiImporter


# important to be distinct from 'test' which ForgeWiki uses, so that the tests can run in parallel and not clobber each other
test_project_with_wiki = 'test2'
with_wiki = with_tool(test_project_with_wiki, 'wiki', 'w', 'wiki')


class TestGitHubRepoImporter(TestCase):

    def _make_project(self, gh_proj_name=None):
        project = Mock()
        project.get_tool_data.side_effect = lambda *args: gh_proj_name
        return project


    @patch('forgeimporters.github.wiki.ThreadLocalORMSession')
    @patch('forgeimporters.github.wiki.g')
    @patch('forgeimporters.github.wiki.GitHubProjectExtractor')
    def test_import_tool_happy_path(self, ghpe, g, tlorms):
        with patch('forgeimporters.github.wiki.GitHubWikiImporter.import_pages'), patch('forgeimporters.github.wiki.c'):
            ghpe.return_value.has_wiki.return_value = True
            p = self._make_project(gh_proj_name='myproject')
            GitHubWikiImporter().import_tool(p, Mock(name='c.user'), project_name='project_name', user_name='testuser')
            p.install_app.assert_called_once_with(
                'Wiki',
                mount_point='wiki',
                mount_label='Wiki')
            g.post_event.assert_called_once_with('project_updated')


class TestGitHubWikiImporter(TestCase):

    def setUp(self):
        setup_basic_test()
        self.blob1 = Mock()
        self.blob1.name = 'Home.md'
        self.blob1.data_stream.read.return_value = '# test message'

        self.blob2 = Mock()
        self.blob2.name = 'Home2.creole'
        self.blob2.data_stream.read.return_value = '**test message**'

        self.blob3 = Mock()
        self.blob3.name = 'Home3.rest'
        self.blob3.data_stream.read.return_value = 'test message'

        self.commit1 = Mock()
        self.commit1.tree.blobs = [self.blob1]
        self.commit1.committed_date = 1256301446

        self.commit2 = Mock()
        self.commit2.tree.blobs = [self.blob1, self.blob2, self.blob3]
        self.commit2.tree.__contains__ = lambda _, item: item in [self.blob1.name, self.blob2.name, self.blob3.name]
        self.commit2.committed_date = 1256291446

    @patch('forgeimporters.github.wiki.WM.Page.upsert')
    @patch('forgeimporters.github.wiki.h.render_any_markup')
    def test_without_history(self, render, upsert):
        self.commit2.tree.blobs = [self.blob2, self.blob3]
        upsert.text = Mock()
        importer = GitHubWikiImporter()
        importer.github_wiki_url = 'https://github.com/a/b/wiki'
        importer.app = Mock()
        importer.app.url = '/p/test/wiki/'
        importer.rewrite_links = Mock(return_value='')
        importer._without_history(self.commit2)
        assert_equal(upsert.call_args_list, [call('Home2'), call('Home3')])

        assert_equal(render.call_args_list, [
            call('Home2.creole', u'**test message**'),
            call('Home3.rest', u'test message')])

    @patch('forgeimporters.github.wiki.git.Repo')
    @patch('forgeimporters.github.wiki.mkdtemp')
    def test_clone_from(self, path, repo):
        with patch('forgeimporters.github.wiki.rmtree'):
            path.return_value = 'temp_path'
            GitHubWikiImporter().import_pages('wiki_url')
            repo.clone_from.assert_called_with('wiki_url', to_path='temp_path', bare=True)

    @patch('forgeimporters.github.wiki.git.Repo._clone')
    @patch('forgeimporters.github.wiki.GitHubWikiImporter._with_history')
    @patch('forgeimporters.github.wiki.GitHubWikiImporter._without_history')
    def test_import_with_history(self, without_history, with_history, clone):
        repo = clone.return_value
        repo.iter_commits.return_value = [self.commit1, self.commit2]
        GitHubWikiImporter().import_pages('wiki_url', history=True)
        assert_equal(with_history.call_count, 2)
        assert_equal(without_history.call_count, 0)

    @patch('forgeimporters.github.wiki.GitHubWikiImporter._with_history')
    @patch('forgeimporters.github.wiki.GitHubWikiImporter._without_history')
    def test_get_commits_without_history(self, without_history, with_history):
        with patch('forgeimporters.github.wiki.git.Repo._clone'):
            GitHubWikiImporter().import_pages('wiki_url')
            assert_equal(with_history.call_count, 0)
            assert_equal(without_history.call_count, 1)

    @patch('forgeimporters.github.wiki.WM.Page.upsert')
    @patch('forgeimporters.github.wiki.h.render_any_markup')
    def test_with_history(self, render, upsert):
        self.commit2.stats.files = {"Home.rst": self.blob1}
        self.commit2.tree = {"Home.rst": self.blob1}
        importer = GitHubWikiImporter()
        importer.github_wiki_url = 'https://github.com/a/b/wiki'
        importer.app = Mock()
        importer.app.url = '/p/test/wiki/'
        importer.rewrite_links = Mock(return_value='')
        importer._with_history(self.commit2)
        assert_equal(upsert.call_args_list, [call('Home')])
        assert_equal(render.call_args_list, [call('Home.rst', u'# test message')])


    @skipif(module_not_available('html2text'))
    @patch('forgeimporters.github.wiki.WM.Page.upsert')
    @patch('forgeimporters.github.wiki.mediawiki2markdown')
    def test_with_history_mediawiki(self, md2mkm, upsert):
        self.commit2.stats.files = {"Home.mediawiki": self.blob1}
        self.commit2.tree = {"Home.mediawiki": self.blob1}
        md2mkm.return_value = u'# test message'
        importer = GitHubWikiImporter()
        importer.github_wiki_url = 'https://github.com/a/b/wiki'
        importer.app = Mock()
        importer.app.url = '/p/test/wiki/'
        importer.rewrite_links = Mock(return_value='')
        importer.convert_gollum_tags = Mock(return_value=u'# test message')
        importer._with_history(self.commit2)
        assert_equal(upsert.call_args_list, [call('Home')])
        assert_equal(md2mkm.call_args_list, [call(u'# test message')])


    def test_convert_page_name(self):
        f = GitHubWikiImporter()._convert_page_name
        assert_equal(f('Page Name'), 'Page Name')
        assert_equal(f('Page-Name'), 'Page Name')
        assert_equal(f('Page / Name'), 'Page   Name')

    def test_convert_gollum_page_links(self):
        f = GitHubWikiImporter().convert_gollum_tags
        assert_equal(f(u'[[Page]]'), u'[Page]')
        assert_equal(f(u'[[Page Title|Page]]'), u'[Page Title](Page)')
        assert_equal(f(u'[[Pagê Nâme]]'), u'[Pagê Nâme]')
        # Github always converts spaces and slashes in links to hyphens,
        # to lookup page in the filesystem. During import we're converting
        # all hyphens in page name to spaces, but still supporting both link formats.
        assert_equal(f(u'[[Page With Spaces]]'), u'[Page With Spaces]')
        assert_equal(f(u'[[Page-With-Spaces]]'), u'[Page With Spaces]')
        assert_equal(f(u'[[Page / 1]]'), u'[Page   1]')
        assert_equal(f(u'[[Title|Page With Spaces]]'), u'[Title](Page With Spaces)')
        assert_equal(f(u'[[Title|Page-With-Spaces]]'), u'[Title](Page With Spaces)')
        assert_equal(f(u'[[go here|Page / 1]]'), u'[go here](Page   1)')

    def test_convert_gollum_page_links_escaped(self):
        f = GitHubWikiImporter().convert_gollum_tags
        assert_equal(f(u"'[[Page]]"), u'[[Page]]')
        assert_equal(f(u"'[[Page Title|Page]]"), u'[[Page Title|Page]]')
        assert_equal(f(u"'[[Page With Spaces]]"), u'[[Page With Spaces]]')
        assert_equal(f(u"'[[Page-With-Spaces]]"), u'[[Page-With-Spaces]]')
        assert_equal(f(u"'[[Page / 1]]"), u'[[Page / 1]]')
        assert_equal(f(u"'[[Title|Page With Spaces]]"), u'[[Title|Page With Spaces]]')
        assert_equal(f(u"'[[Title|Page-With-Spaces]]"), u'[[Title|Page-With-Spaces]]')
        assert_equal(f(u"'[[go here|Page / 1]]"), u'[[go here|Page / 1]]')

    def test_convert_gollum_external_links(self):
        f = GitHubWikiImporter().convert_gollum_tags
        assert_equal(f(u'[[http://sf.net]]'), u'<http://sf.net>')
        assert_equal(f(u'[[https://sf.net]]'), u'<https://sf.net>')
        assert_equal(f(u'[[SourceForge|http://sf.net]]'), u'[SourceForge](http://sf.net)')

    def test_convert_gollum_external_links_escaped(self):
        f = GitHubWikiImporter().convert_gollum_tags
        assert_equal(f(u"'[[http://sf.net]]"), u'[[http://sf.net]]')
        assert_equal(f(u"'[[https://sf.net]]"), u'[[https://sf.net]]')
        assert_equal(f(u"'[[SourceForge|http://sf.net]]"), u'[[SourceForge|http://sf.net]]')

    def test_convert_gollum_toc(self):
        f = GitHubWikiImporter().convert_gollum_tags
        assert_equal(f(u'[[_TOC_]]'), u'[TOC]')
        assert_equal(f(u"'[[_TOC_]]"), u'[[_TOC_]]')

    def test_convert_gollum_tags(self):
        f = GitHubWikiImporter().convert_gollum_tags
        source = u'''Look at [[this page|Some Page]]

More info at: [[MoreInfo]] [[Even More Info]]

Our website is [[http://sf.net]].

'[[Escaped Tag]]'''

        result = u'''Look at [this page](Some Page)

More info at: [MoreInfo] [Even More Info]

Our website is <http://sf.net>.

[[Escaped Tag]]'''

        assert_equal(f(source), result)

    @skipif(module_not_available('html2text'))
    def test_convert_markup(self):
        importer = GitHubWikiImporter()
        importer.github_wiki_url = 'https://github.com/a/b/wiki'
        importer.app = Mock()
        importer.app.url = '/p/test/wiki/'
        f = importer.convert_markup
        source = u'''Look at [[this page|Some Page]]

More info at: [[MoreInfo]] [[Even More Info]]

Our website is [[http://sf.net]].

'[[Escaped Tag]]

[External link to the wiki page](https://github.com/a/b/wiki/Page)

[External link](https://github.com/a/b/issues/1)'''

        # markdown should be untouched
        assert_equal(f(source, 'test.md'), source)

        assert_equal(f(u'h1. Hello', 't.textile').strip(), u'# Hello')

    @without_module('html2text')
    def test_convert_markup_without_html2text(self):
        importer = GitHubWikiImporter()
        importer.github_wiki_url = 'https://github.com/a/b/wiki'
        importer.app = Mock()
        importer.app.url = '/p/test/wiki/'
        f = importer.convert_markup
        source = u'''Look at [[this page|Some Page]]

More info at: [[MoreInfo]] [[Even More Info]]

Our website is [[http://sf.net]].

'[[Escaped Tag]]

[External link to the wiki page](https://github.com/a/b/wiki/Page)

[External link](https://github.com/a/b/issues/1)'''

        result = u'''<p>Look at [[this page|Some Page]]</p>
<p>More info at: [[MoreInfo]] [[Even More Info]]</p>
<p>Our website is [[http://sf.net]].</p>
<p>'[[Escaped Tag]]</p>
<p>[External link to the wiki page](https://github.com/a/b/wiki/Page)</p>
<p>[External link](https://github.com/a/b/issues/1)</p>'''

        assert_equal(f(source, 'test.textile').strip(), result)

    def test_rewrite_links(self):
        f = GitHubWikiImporter().rewrite_links
        prefix = 'https://github/a/b/wiki'
        new = '/p/test/wiki/'
        assert_equal(f(u'<a href="https://github/a/b/wiki/Test Page">Test Page</a>', prefix, new),
                     u'<a href="/p/test/wiki/Test Page">Test Page</a>')
        assert_equal(f(u'<a href="https://github/a/b/wiki/Test-Page">Test-Page</a>', prefix, new),
                     u'<a href="/p/test/wiki/Test Page">Test Page</a>')
        assert_equal(f(u'<a href="https://github/a/b/issues/1" class="1"></a>', prefix, new),
                     u'<a href="https://github/a/b/issues/1" class="1"></a>')
        assert_equal(f(u'<a href="https://github/a/b/wiki/Test Page">https://github/a/b/wiki/Test Page</a>', prefix, new),
                     u'<a href="/p/test/wiki/Test Page">/p/test/wiki/Test Page</a>')
        assert_equal(f(u'<a href="https://github/a/b/wiki/Test Page">Test <b>Page</b></a>', prefix, new),
                     u'<a href="/p/test/wiki/Test Page">Test <b>Page</b></a>')

    @skipif(module_not_available('html2text'))
    def test_convert_markup_with_mediawiki2markdown(self):
        importer = GitHubWikiImporter()
        importer.github_wiki_url = 'https://github.com/a/b/wiki'
        importer.app = Mock()
        importer.app.url = '/p/test/wiki/'
        f = importer.convert_markup
        source = u'''
''Al'fredas 235 BC''
== See also ==
* [https://github.com/a/b/wiki/AgentSpring-running-instructions-for-d13n-model Test1]
* [https://github.com/a/b/wiki/AgentSpring-conventions Test2]
* [https://github.com/a/b/wiki/AgentSpring-Q&A Test3]
* [https://github.com/a/b/wiki/Extensions Test4]'''

        result = u'''_Al'fredas 235 BC_

## See also

  * [Test1](/p/test/wiki/AgentSpring running instructions for d13n model)
  * [Test2](/p/test/wiki/AgentSpring conventions)
  * [Test3](/p/test/wiki/AgentSpring Q&A)
  * [Test4](/p/test/wiki/Extensions)
'''

        assert_equal(f(source, 'test.mediawiki'), result)

    @skipif(module_not_available('html2text'))
    def test_convert_textile_no_leading_tabs(self):
        importer = GitHubWikiImporter()
        importer.github_wiki_url = 'https://github.com/a/b/wiki'
        importer.app = Mock()
        importer.app.url = '/p/test/wiki/'
        f = importer.convert_markup
        source = u'''h1. Header 1

Some text 1.

h2. Header 2

See [[Page]]'''

        result = u'''# Header 1

Some text 1.

## Header 2

See [Page]'''
        assert_equal(f(source, 'test.textile').strip(), result)

    @skipif(module_not_available('html2text'))
    def test_convert_markup_with_amp_in_links(self):
        importer = GitHubWikiImporter()
        importer.github_wiki_url = 'https://github.com/a/b/wiki'
        importer.app = Mock()
        importer.app.url = '/p/test/wiki/'
        f = importer.convert_markup
        source = u'[[Ticks & Leeches]]'
        result = u'[Ticks & Leeches]'
        # markdown should be untouched
        assert_equal(f(source, 'test.textile').strip(), result)


class TestGitHubWikiImportController(TestController, TestCase):

    url = '/p/%s/admin/ext/import/github-wiki/' % test_project_with_wiki

    @with_wiki
    def test_index(self):
        r = self.app.get(self.url)
        self.assertIsNotNone(r.html.find(attrs=dict(name='gh_user_name')))
        self.assertIsNotNone(r.html.find(attrs=dict(name='gh_project_name')))
        self.assertIsNotNone(r.html.find(attrs=dict(name='mount_label')))
        self.assertIsNotNone(r.html.find(attrs=dict(name='mount_point')))
        self.assertIsNotNone(r.html.find(attrs=dict(name='tool_option', value='import_history')))

    @with_wiki
    @patch('forgeimporters.github.wiki.import_tool')
    def test_create(self, import_tool):
        params = dict(
            gh_user_name='spooky',
            gh_project_name='mulder',
            mount_point='gh-wiki',
            mount_label='GitHub Wiki',
            tool_option='import_history')
        r = self.app.post(self.url + 'create', params, status=302)
        self.assertEqual(r.location, 'http://localhost/p/%s/admin/' % test_project_with_wiki)
        args = import_tool.post.call_args[1]
        self.assertEqual(u'GitHub Wiki', args['mount_label'])
        self.assertEqual(u'gh-wiki', args['mount_point'])
        self.assertEqual(u'mulder', args['project_name'])
        self.assertEqual(u'spooky', args['user_name'])
        self.assertEqual(u'import_history', args['tool_option'])

        # without history
        params.pop('tool_option')
        r = self.app.post(self.url + 'create', params, status=302)
        self.assertEqual(r.location, 'http://localhost/p/%s/admin/' % test_project_with_wiki)
        args = import_tool.post.call_args[1]
        self.assertEqual(u'GitHub Wiki', args['mount_label'])
        self.assertEqual(u'gh-wiki', args['mount_point'])
        self.assertEqual(u'mulder', args['project_name'])
        self.assertEqual(u'spooky', args['user_name'])
        self.assertEqual(u'', args['tool_option'])
