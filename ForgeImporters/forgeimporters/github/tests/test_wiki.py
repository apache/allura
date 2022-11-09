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

from unittest import TestCase, skipIf
from mock import Mock, patch, call
from ming.odm import ThreadLocalORMSession
import git

from allura import model as M
from allura.tests import TestController
from allura.tests.decorators import with_tool, without_module
from alluratest.controller import setup_basic_test
from alluratest.tools import module_not_available
from forgeimporters.github.wiki import GitHubWikiImporter
from forgeimporters.github.utils import GitHubMarkdownConverter
from forgeimporters.github import GitHubOAuthMixin


# important to be distinct from 'test' which ForgeWiki uses, so that the
# tests can run in parallel and not clobber each other
test_project_with_wiki = 'test2'
with_wiki = with_tool(test_project_with_wiki, 'wiki', 'w', 'wiki')


class TestGitHubWikiImporter(TestCase):

    def _make_project(self, gh_proj_name=None):
        project = Mock()
        project.get_tool_data.side_effect = lambda *args: gh_proj_name
        return project

    @patch('forgeimporters.github.wiki.M')
    @patch('forgeimporters.github.wiki.ThreadLocalORMSession')
    @patch('forgeimporters.github.wiki.g')
    @patch('forgeimporters.github.wiki.GitHubProjectExtractor')
    def test_import_tool_happy_path(self, ghpe, g, tlorms, M):
        with patch('forgeimporters.github.wiki.GitHubWikiImporter.import_pages'),\
                patch('forgeimporters.github.wiki.GitHubWikiImporter.has_wiki_repo', return_value=True),\
                patch('forgeimporters.github.wiki.c'):
            ghpe.return_value.has_wiki.return_value = True
            p = self._make_project(gh_proj_name='myproject')
            u = Mock(name='c.user')
            app = p.install_app.return_value
            app.config.options.mount_point = 'wiki'
            app.url = 'foo'
            GitHubWikiImporter().import_tool(
                p, u, project_name='project_name', user_name='testuser')
            p.install_app.assert_called_once_with(
                'Wiki',
                mount_point='wiki',
                mount_label='Wiki',
                import_id={
                    'source': 'GitHub',
                    'project_name': 'testuser/project_name',
                }
            )
            M.AuditLog.log.assert_called_once_with(
                'import tool wiki from testuser/project_name on GitHub',
                project=p, user=u, url='foo')
            g.post_event.assert_called_once_with('project_updated')

    def setup_method(self, method):
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
        blobs = [self.blob1, self.blob2, self.blob3]
        self.commit2.tree.blobs = blobs
        self.commit2.tree.__contains__ = lambda _, item: item in [
            self.blob1.name, self.blob2.name, self.blob3.name]
        self.commit2.tree.traverse.return_value = blobs
        self.commit2.committed_date = 1256291446

    @patch('forgeimporters.github.wiki.WM.Page.upsert')
    def test_import_id(self, upsert):
        page = Mock()
        upsert.return_value = page
        importer = GitHubWikiImporter()
        importer.app = Mock()
        importer.app.config.options = {
            'import_id': {
                'source': 'GitHub',
                'project_name': 'me/project',
            }
        }
        importer._make_page('text', 'Page.md', self.commit2)
        import_id = {
            'source': 'GitHub',
            'project_name': 'me/project',
            'source_id': 'Page',
        }
        assert page.import_id == import_id

    @patch('forgeimporters.github.wiki.WM.Page.upsert')
    @patch('forgeimporters.github.wiki.h.render_any_markup')
    def test_without_history(self, render, upsert):
        self.commit2.tree.blobs = [self.blob2, self.blob3]
        upsert.text = Mock()
        importer = GitHubWikiImporter()
        importer.github_wiki_url = 'https://github.com/a/b/wiki'
        importer.app = Mock()
        importer.app.config.options = {}
        importer.app.url = '/p/test/wiki/'
        importer.rewrite_links = Mock(return_value='')
        importer._without_history(self.commit2)
        assert upsert.call_args_list == [call('Home2'), call('Home3')]

        assert render.call_args_list == [
            call('Home2.creole', '**test message**'),
            call('Home3.rest', 'test message')]

    @patch('forgeimporters.github.wiki.git.Repo')
    @patch('forgeimporters.github.wiki.mkdtemp')
    def test_clone_from(self, path, repo):
        with patch('forgeimporters.github.wiki.rmtree'):
            path.return_value = 'temp_path'
            GitHubWikiImporter().import_pages('wiki_url')
            repo.clone_from.assert_called_with(
                'wiki_url', to_path='temp_path', bare=True)

    @patch('forgeimporters.github.wiki.git.Repo._clone')
    @patch('forgeimporters.github.wiki.GitHubWikiImporter._with_history')
    @patch('forgeimporters.github.wiki.GitHubWikiImporter._without_history')
    def test_import_with_history(self, without_history, with_history, clone):
        repo = clone.return_value
        repo.iter_commits.return_value = [self.commit1, self.commit2]
        GitHubWikiImporter().import_pages('wiki_url', history=True)
        assert with_history.call_count == 2
        assert without_history.call_count == 0

    @patch('forgeimporters.github.wiki.GitHubWikiImporter._with_history')
    @patch('forgeimporters.github.wiki.GitHubWikiImporter._without_history')
    def test_get_commits_without_history(self, without_history, with_history):
        with patch('forgeimporters.github.wiki.git.Repo._clone'):
            GitHubWikiImporter().import_pages('wiki_url')
            assert with_history.call_count == 0
            assert without_history.call_count == 1

    @patch('forgeimporters.github.wiki.WM.Page.upsert')
    @patch('forgeimporters.github.wiki.h.render_any_markup')
    def test_with_history(self, render, upsert):
        self.commit2.stats.files = {"Home.rst": self.blob1}
        self.commit2.tree = {"Home.rst": self.blob1}
        importer = GitHubWikiImporter()
        importer._set_available_pages = Mock()
        importer.github_wiki_url = 'https://github.com/a/b/wiki'
        importer.app = Mock()
        importer.app.config.options = {}
        importer.app.url = '/p/test/wiki/'
        importer.rewrite_links = Mock(return_value='')
        importer._with_history(self.commit2)
        assert upsert.call_args_list == [call('Home')]
        assert (render.call_args_list ==
                [call('Home.rst', '# test message')])

    @skipIf(module_not_available('html2text'), 'html2text required')
    @patch('forgeimporters.github.wiki.WM.Page.upsert')
    @patch('forgeimporters.github.wiki.mediawiki2markdown')
    def test_with_history_mediawiki(self, md2mkm, upsert):
        self.commit2.stats.files = {"Home.mediawiki": self.blob1}
        self.commit2.tree = {"Home.mediawiki": self.blob1}
        md2mkm.return_value = '# test message'
        importer = GitHubWikiImporter()
        importer._set_available_pages = Mock()
        importer.github_wiki_url = 'https://github.com/a/b/wiki'
        importer.app = Mock()
        importer.app.config.options = {}
        importer.app.url = '/p/test/wiki/'
        importer.rewrite_links = Mock(return_value='')
        importer.convert_gollum_tags = Mock(return_value='# test message')
        importer._with_history(self.commit2)
        assert upsert.call_args_list == [call('Home')]
        assert md2mkm.call_args_list == [call('# test message')]

    def test_set_available_pages(self):
        importer = GitHubWikiImporter()
        commit = Mock()
        blobs = [Mock() for i in range(3)]
        blobs[0].name = 'Home-42.md'
        blobs[1].name = 'image.png'
        blobs[2].name = 'code & fun.textile'
        commit.tree.traverse.return_value = blobs
        importer._set_available_pages(commit)
        assert importer.available_pages == ['Home 42', 'code & fun']

    def test_gollum_page_links_case_insensitive(self):
        i = GitHubWikiImporter()
        i.available_pages = ['Home 42', 'code & fun']
        assert i.convert_gollum_tags('[[Code & Fun]]') == '[code & fun]'
        assert i.convert_gollum_tags('[[home-42]]') == '[Home 42]'
        assert i.convert_gollum_tags('[[Unknown]]') == '[Unknown]'

    def test_convert_page_name(self):
        f = GitHubWikiImporter()._convert_page_name
        assert f('Page Name') == 'Page Name'
        assert f('Page-Name') == 'Page Name'
        assert f('Page / Name') == 'Page   Name'

    def test_convert_gollum_page_links(self):
        f = GitHubWikiImporter().convert_gollum_tags
        assert f('[[Page]]') == '[Page]'
        assert f('[[Page Title|Page]]') == '[Page Title](Page)'
        assert f('[[Pagê Nâme]]') == '[Pagê Nâme]'
        # Github always converts spaces and slashes in links to hyphens,
        # to lookup page in the filesystem. During import we're converting
        # all hyphens in page name to spaces, but still supporting both link
        # formats.
        assert f('[[Page With Spaces]]') == '[Page With Spaces]'
        assert f('[[Page-With-Spaces]]') == '[Page With Spaces]'
        assert f('[[Page / 1]]') == '[Page   1]'
        assert (f('[[Title|Page With Spaces]]') ==
                '[Title](Page With Spaces)')
        assert (f('[[Title|Page-With-Spaces]]') ==
                '[Title](Page With Spaces)')
        assert f('[[go here|Page / 1]]') == '[go here](Page   1)'

    def test_convert_gollum_page_links_escaped(self):
        f = GitHubWikiImporter().convert_gollum_tags
        assert f("'[[Page]]") == '[[Page]]'
        assert f("'[[Page Title|Page]]") == '[[Page Title|Page]]'
        assert f("'[[Page With Spaces]]") == '[[Page With Spaces]]'
        assert f("'[[Page-With-Spaces]]") == '[[Page-With-Spaces]]'
        assert f("'[[Page / 1]]") == '[[Page / 1]]'
        assert (f("'[[Title|Page With Spaces]]") ==
                '[[Title|Page With Spaces]]')
        assert (f("'[[Title|Page-With-Spaces]]") ==
                '[[Title|Page-With-Spaces]]')
        assert f("'[[go here|Page / 1]]") == '[[go here|Page / 1]]'

    def test_convert_gollum_external_links(self):
        f = GitHubWikiImporter().convert_gollum_tags
        assert f('[[http://domain.net]]') == '<http://domain.net>'
        assert f('[[https://domain.net]]') == '<https://domain.net>'
        assert (f('[[Site|http://domain.net]]') ==
                '[Site](http://domain.net)')

    def test_convert_gollum_external_links_escaped(self):
        f = GitHubWikiImporter().convert_gollum_tags
        assert f("'[[http://domain.net]]") == '[[http://domain.net]]'
        assert f("'[[https://domain.net]]") == '[[https://domain.net]]'
        assert (f("'[[Site|http://domain.net]]") ==
                '[[Site|http://domain.net]]')

    def test_convert_gollum_toc(self):
        f = GitHubWikiImporter().convert_gollum_tags
        assert f('[[_TOC_]]') == '[TOC]'
        assert f("'[[_TOC_]]") == '[[_TOC_]]'

    def test_convert_gollum_tags(self):
        f = GitHubWikiImporter().convert_gollum_tags
        source = '''Look at [[this page|Some Page]]

More info at: [[MoreInfo]] [[Even More Info]]

Our website is [[http://domain.net]].

'[[Escaped Tag]]'''

        result = '''Look at [this page](Some Page)

More info at: [MoreInfo] [Even More Info]

Our website is <http://domain.net>.

[[Escaped Tag]]'''

        assert f(source) == result

    @skipIf(module_not_available('html2text'), 'html2text required')
    def test_convert_markup(self):
        importer = GitHubWikiImporter()
        importer.github_wiki_url = 'https://github.com/a/b/wiki'
        importer.app = Mock()
        importer.app.url = '/p/test/wiki/'
        importer.github_markdown_converter = GitHubMarkdownConverter(
            'user', 'proj')
        f = importer.convert_markup
        source = '''Look at [[this page|Some Page]]

More info at: [[MoreInfo]] [[Even More Info]]

Our website is [[http://domain.net]].

'[[Escaped Tag]]

```python
codeblock
```

ticket #1

#1 header

sha aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'''
        result = '''Look at [this page](Some Page)

More info at: [MoreInfo] [Even More Info]

Our website is <http://domain.net>.

[[Escaped Tag]]

    :::python
    codeblock

ticket [#1]

[#1] header

sha [aaaaaa]'''
        assert f(source, 'test.md').strip() == result

        assert f('h1. Hello', 't.textile').strip() == '# Hello'

    @without_module('html2text')
    def test_convert_markup_without_html2text(self):
        importer = GitHubWikiImporter()
        importer.github_wiki_url = 'https://github.com/a/b/wiki'
        importer.app = Mock()
        importer.app.url = '/p/test/wiki/'
        f = importer.convert_markup
        source = '''Look at [[this page|Some Page]]

More info at: [[MoreInfo]] [[Even More Info]]

Our website is [[http://domain.net]].

'[[Escaped Tag]]

[External link to the wiki page](https://github.com/a/b/wiki/Page)

[External link](https://github.com/a/b/issues/1)'''

        result = '''<p>Look at [[this page|Some Page]]</p>
<p>More info at: [[MoreInfo]] [[Even More Info]]</p>
<p>Our website is [[http://domain.net]].</p>
<p>\u2018[[Escaped Tag]]</p>
<p>[External link to the wiki page](https://github.com/a/b/wiki/Page)</p>
<p>[External link](https://github.com/a/b/issues/1)</p>'''

        assert f(source, 'test.textile').strip() == result

    def test_rewrite_links(self):
        f = GitHubWikiImporter().rewrite_links
        prefix = 'https://github/a/b/wiki'
        new = '/p/test/wiki/'
        assert (
            f('<a href="https://github/a/b/wiki/Test Page">Test Page</a>',
              prefix, new) ==
            '<a href="/p/test/wiki/Test Page">Test Page</a>')
        assert (
            f('<a href="https://github/a/b/wiki/Test-Page">Test-Page</a>',
              prefix, new) ==
            '<a href="/p/test/wiki/Test Page">Test Page</a>')
        assert (
            f('<a href="https://github/a/b/issues/1" class="1"></a>',
              prefix, new) ==
            '<a class="1" href="https://github/a/b/issues/1"></a>')
        assert (
            f('<a href="https://github/a/b/wiki/Test Page">https://github/a/b/wiki/Test Page</a>',
              prefix, new) ==
            '<a href="/p/test/wiki/Test Page">/p/test/wiki/Test Page</a>')
        assert (
            f('<a href="https://github/a/b/wiki/Test Page">Test blah blah</a>',
              prefix, new) ==
            '<a href="/p/test/wiki/Test Page">Test blah blah</a>')
        assert (
            f('<a href="https://github/a/b/wiki/Test Page">Test <b>Page</b></a>',
              prefix, new) ==
            '<a href="/p/test/wiki/Test Page">Test <b>Page</b></a>')

    @skipIf(module_not_available('html2text'), 'html2text required')
    def test_convert_markup_with_mediawiki2markdown(self):
        importer = GitHubWikiImporter()
        importer.github_wiki_url = 'https://github.com/a/b/wiki'
        importer.app = Mock()
        importer.app.url = '/p/test/wiki/'
        f = importer.convert_markup
        source = '''
''Al'fredas 235 BC''
== See also ==
* [https://github.com/a/b/wiki/AgentSpring-running-instructions-for-d13n-model Test1]
* [https://github.com/a/b/wiki/AgentSpring-conventions Test2]
* [https://github.com/a/b/wiki/AgentSpring-Q&A Test3]
* [https://github.com/a/b/wiki/Extensions Test4]'''

        result = '''_Al'fredas 235 BC_

## See also

  * [Test1](/p/test/wiki/AgentSpring running instructions for d13n model)
  * [Test2](/p/test/wiki/AgentSpring conventions)
  * [Test3](/p/test/wiki/AgentSpring Q&A)
  * [Test4](/p/test/wiki/Extensions)

'''

        assert f(source, 'test.mediawiki') == result

    @skipIf(module_not_available('html2text'), 'html2text required')
    def test_convert_textile_no_leading_tabs(self):
        importer = GitHubWikiImporter()
        importer.github_wiki_url = 'https://github.com/a/b/wiki'
        importer.app = Mock()
        importer.app.url = '/p/test/wiki/'
        f = importer.convert_markup
        source = '''h1. Header 1

Some text 1.

h2. Header 2

See [[Page]]'''

        result = '''# Header 1

Some text 1.

## Header 2

See [Page]'''
        assert f(source, 'test.textile').strip() == result

    @skipIf(module_not_available('html2text'), 'html2text required')
    def test_convert_markup_with_amp_in_links(self):
        importer = GitHubWikiImporter()
        importer.github_wiki_url = 'https://github.com/a/b/wiki'
        importer.app = Mock()
        importer.app.url = '/p/test/wiki/'
        f = importer.convert_markup
        source = '[[Ticks & Leeches]]'
        result = '[Ticks & Leeches]'
        # markdown should be untouched
        assert f(source, 'test.rst').strip() == result

    @skipIf(module_not_available('html2text'), 'html2text required')
    def test_convert_markup_textile(self):
        importer = GitHubWikiImporter()
        importer.github_wiki_url = 'https://github.com/a/b/wiki'
        importer.app = Mock()
        importer.app.url = '/p/test/wiki/'
        f = importer.convert_markup

        # check if lists converting works properly
        source = '''There are good reasons for this:

  # Duplicate libraries regularly break builds
  # Subtle bugs emerge with duplicate libraries, and to a lesser extent, duplicate tools
  # We want you to try harder to make your formula work with what OS X comes with
'''
        result = '''There are good reasons for this:

  1. Duplicate libraries regularly break builds
  2. Subtle bugs emerge with duplicate libraries, and to a lesser extent, duplicate tools
  3. We want you to try harder to make your formula work with what OS X comes with

'''

        assert f(source, 'test.textile') == result

        # textile-style links converts normal
        source = '*"Textile":Troubleshooting*'
        result = '**[Textile](Troubleshooting)**\n\n'
        assert f(source, 'test2.textile') == result

        # links with formatting converts normal in textile now
        source = '''*[[this checklist|Troubleshooting]]*

some text and *[[Tips n' Tricks]]*

*[[link|http://otherlink.com]]*
'''
        result = '''**[this checklist](Troubleshooting)**

some text and **[Tips n\u2019 Tricks]**

**[link](http://otherlink.com)**

'''
        assert f(source, 'test3.textile') == result

    @skipIf(module_not_available('html2text'), 'html2text required')
    def test_convert_textile_special_tag(self):
        importer = GitHubWikiImporter()
        importer.github_wiki_url = 'https://github.com/a/b/wiki'
        importer.app = Mock()
        importer.app.url = '/p/test/wiki/'
        f = importer.convert_markup
        source = '*[[this checklist|Troubleshooting]]*'
        assert (f(source, 't.textile').strip() ==
                '**[this checklist](Troubleshooting)**')

    @without_module('html2text')
    def test_convert_textile_special_tag_without_html2text(self):
        importer = GitHubWikiImporter()
        importer.github_wiki_url = 'https://github.com/a/b/wiki'
        importer.app = Mock()
        importer.app.url = '/p/test/wiki/'
        f = importer.convert_markup
        source = '*[[this checklist|Troubleshooting]]*'
        result = '<p><strong>[[this checklist|Troubleshooting]]</strong></p>'
        assert f(source, 't.textile').strip() == result

    @patch('forgeimporters.github.wiki.mkdtemp', autospec=True)
    @patch('forgeimporters.github.wiki.rmtree', autospec=True)
    @patch('forgeimporters.github.wiki.git.Repo', autospec=True)
    def test_has_wiki_repo(self, repo, rmtree, mkdtemp):
        mkdtemp.return_value = 'fake path'
        i = GitHubWikiImporter()
        assert i.has_wiki_repo('fake url') is True
        repo.clone_from.assert_called_once_with(
            'fake url', to_path='fake path', bare=True)
        rmtree.assert_called_once_with('fake path')

        def raise_error(*args, **kw):
            raise git.GitCommandError('bam', 'bam', 'bam')
        repo.clone_from.side_effect = raise_error
        assert i.has_wiki_repo('fake url') is False


class TestGitHubWikiImportController(TestController, TestCase):

    url = '/p/%s/admin/ext/import/github-wiki/' % test_project_with_wiki

    @with_wiki
    def test_index(self):
        r = self.app.get(self.url)
        self.assertIsNotNone(r.html.find(attrs=dict(name='gh_user_name')))
        self.assertIsNotNone(r.html.find(attrs=dict(name='gh_project_name')))
        self.assertIsNotNone(r.html.find(attrs=dict(name='mount_label')))
        self.assertIsNotNone(r.html.find(attrs=dict(name='mount_point')))
        self.assertIsNotNone(
            r.html.find(attrs=dict(name='tool_option', value='import_history')))

    @with_wiki
    @patch('forgeimporters.github.requests')
    @patch('forgeimporters.base.import_tool')
    def test_create(self, import_tool, requests):
        requests.head.return_value.status_code = 200
        params = dict(
            gh_user_name='spooky',
            gh_project_name='mulder',
            mount_point='gh-wiki',
            mount_label='GitHub Wiki',
            tool_option='import_history')
        r = self.app.post(self.url + 'create', params, status=302)
        self.assertEqual(r.location, 'http://localhost/p/%s/admin/' %
                         test_project_with_wiki)
        args = import_tool.post.call_args[1]
        self.assertEqual('GitHub Wiki', args['mount_label'])
        self.assertEqual('gh-wiki', args['mount_point'])
        self.assertEqual('mulder', args['project_name'])
        self.assertEqual('spooky', args['user_name'])
        self.assertEqual('import_history', args['tool_option'])
        self.assertEqual(requests.head.call_count, 1)

    @with_wiki
    @patch('forgeimporters.github.requests')
    @patch('forgeimporters.base.import_tool')
    def test_create_without_history(self, import_tool, requests):
        requests.head.return_value.status_code = 200
        params = dict(
            gh_user_name='spooky',
            gh_project_name='mulder',
            mount_point='gh-wiki',
            mount_label='GitHub Wiki'
        )
        r = self.app.post(self.url + 'create', params, status=302)
        self.assertEqual(r.location, 'http://localhost/p/%s/admin/' %
                         test_project_with_wiki)
        args = import_tool.post.call_args[1]
        self.assertEqual('GitHub Wiki', args['mount_label'])
        self.assertEqual('gh-wiki', args['mount_point'])
        self.assertEqual('mulder', args['project_name'])
        self.assertEqual('spooky', args['user_name'])
        self.assertEqual('', args['tool_option'])
        self.assertEqual(requests.head.call_count, 1)

    @with_wiki
    @patch('forgeimporters.github.requests')
    @patch('forgeimporters.base.import_tool')
    def test_create_limit(self, import_tool, requests):
        requests.head.return_value.status_code = 200
        p = M.Project.query.get(shortname=test_project_with_wiki)
        p.set_tool_data('GitHubWikiImporter', pending=1)
        ThreadLocalORMSession.flush_all()
        params = dict(
            gh_user_name='spooky',
            gh_project_name='mulder',
            mount_point='gh-wiki',
            mount_label='GitHub Wiki')
        r = self.app.post(self.url + 'create', params, status=302).follow()
        self.assertIn('Please wait and try again', r)
        self.assertEqual(import_tool.post.call_count, 0)

    @with_wiki
    @patch.object(GitHubOAuthMixin, 'oauth_begin')
    def test_oauth(self, oauth_begin):
        self.app.get(self.url)
        self.assertEqual(oauth_begin.call_count, 1)
