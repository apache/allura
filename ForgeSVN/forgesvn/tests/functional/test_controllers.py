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

import json
import shutil
import os
from unittest import skipUnless

import tg
import pkg_resources
from tg import tmpl_context as c
from ming.orm import ThreadLocalORMSession
from mock import patch

from allura import model as M
from allura.lib import helpers as h
from alluratest.controller import TestController
from forgesvn.tests import with_svn
from allura.tests.decorators import with_tool


class SVNTestController(TestController):

    def setup_method(self, method):
        super().setup_method(method)
        self.setup_with_tools()

    def _make_app(self, mount_point, name):
        h.set_context('test', mount_point, neighborhood='Projects')
        repo_dir = pkg_resources.resource_filename(
            'forgesvn', 'tests/data/')
        c.app.repo.fs_path = repo_dir
        c.app.repo.status = 'ready'
        c.app.repo.name = name
        c.app.repo.refresh()
        if os.path.isdir(c.app.repo.tarball_path):
            shutil.rmtree(c.app.repo.tarball_path.encode('utf-8'))
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    @with_svn
    @with_tool('test', 'SVN', 'svn-tags', 'SVN with tags')
    def setup_with_tools(self):
        self._make_app('svn-tags', 'testsvn-trunk-tags-branches')
        self._make_app('src', 'testsvn')


class TestRootController(SVNTestController):

    def test_head(self):
        r = self.app.get('/src/')
        assert r.location.endswith('/src/HEAD/tree/')

    def test_status(self):
        resp = self.app.get('/src/status')
        d = json.loads(resp.text)
        assert d == dict(status='ready')

    def test_status_html(self):
        resp = self.app.get('/src/').follow()
        # repo status not displayed if 'ready'
        assert resp.html.find('div', dict(id='repo_status')) is None
        h.set_context('test', 'src', neighborhood='Projects')
        c.app.repo.status = 'analyzing'
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        # repo status displayed if not 'ready'
        resp = self.app.get('/src/').follow()
        div = resp.html.find('div', dict(id='repo_status'))
        assert div.span.text == 'analyzing'

    def test_index(self):
        resp = self.app.get('/src/').follow()
        assert 'svn checkout' in resp
        assert '[r5]' in resp, resp.showbrowser()

    def test_index_empty(self):
        resp = self.app.get('/svn/')
        resp.mustcontain('Create default directories')

    def test_commit_browser(self):
        self.app.get('/src/commit_browser')

    def test_commit_browser_data(self):
        resp = self.app.get('/src/commit_browser_data')
        data = json.loads(resp.text)
        assert data['max_row'] == 6
        assert data['next_column'] == 1
        for val in data['built_tree'].values():
            if val['url'] == '/p/test/src/1/':
                assert val['short_id'] == '[r1]'
                assert val['column'] == 0
                assert val['row'] == 6
                assert val['message'] == 'Create readme'

    def test_feed(self):
        for ext in ['', '.rss']:
            r = self.app.get('/src/feed%s' % ext)
            channel = r.xml.find('channel')
            title = channel.find('title').text
            assert title == 'test SVN changes'
            description = channel.find('description').text
            assert (description ==
                    'Recent changes to SVN repository in test project')
            link = channel.find('link').text
            assert link == 'http://localhost/p/test/src/'
            earliest_commit = channel.findall('item')[-1]
            assert earliest_commit.find('title').text == 'Create readme'
            link = 'http://localhost/p/test/src/1/'
            assert earliest_commit.find('link').text == link
            assert earliest_commit.find('guid').text == link
        # .atom has slightly different structure
        prefix = '{http://www.w3.org/2005/Atom}'
        r = self.app.get('/src/feed.atom')
        title = r.xml.find(prefix + 'title').text
        assert title == 'test SVN changes'
        link = r.xml.find(prefix + 'link').attrib['href']
        assert link == 'http://localhost/p/test/src/'
        earliest_commit = r.xml.findall(prefix + 'entry')[-1]
        assert earliest_commit.find(prefix + 'title').text == 'Create readme'
        link = 'http://localhost/p/test/src/1/'
        assert earliest_commit.find(prefix + 'link').attrib['href'] == link

    def test_commit(self):
        resp = self.app.get('/src/3/tree/')
        assert len(resp.html.findAll('tr')) == 3, resp.showbrowser()

    def test_commit_unicode_and_special_chars(self):
        resp = self.app.get('/src/6/')
        file_url = resp.html.find("a", string="/ЗРЯЧИЙ_ТА_ПОБАЧИТЬ")['href']
        resp = self.app.get(file_url)
        assert ('This is readme' in  # same content as the README file actually
                resp.html.select_one('.codebrowser').text)

        resp = self.app.get('/src/7/')
        print('file links on /src/7/ are:\n\t{}'.format(
            '\n\t'.join(str(t) for t in resp.html.select('.inline-diff a'))))
        file_url = resp.html.find("a", string="/with%2Furlquote-literal.txt")['href']
        file_resp = self.app.get(file_url)
        assert ('%2F means /' in
                file_resp.html.select_one('.codebrowser').text)

        file_url = resp.html.find("a", string='/with-percent%.txt')['href']
        file_resp = self.app.get(file_url)
        assert ('%%%' in
                file_resp.html.select_one('.codebrowser').text)

        file_url = resp.html.find("a", string="/with space.txt")['href']
        file_resp = self.app.get(file_url)
        assert ('spaces' in
                file_resp.html.select_one('.codebrowser').text)

        file_url = resp.html.find("a", string='/with"&:specials.txt')['href']
        file_resp = self.app.get(file_url)
        assert ('"&: encodes as %22%26%3A' in
                file_resp.html.select_one('.codebrowser').text)

    def test_tree(self):
        resp = self.app.get('/src/1/tree/')
        assert len(resp.html.findAll('tr')) == 2, resp.showbrowser()
        resp = self.app.get('/src/3/tree/a/')
        assert len(resp.html.findAll('tr')) == 2, resp.showbrowser()

    def test_file(self):
        resp = self.app.get('/src/1/tree/README')
        assert 'README' in resp.html.find('h2', {'class': 'dark title'}).find('span').contents[4]
        content = str(resp.html.find('div', {'class': 'clip grid-19 codebrowser'}))
        assert 'This is readme' in content, content
        assert '<span id="l1" class="code_block">' in resp
        assert 'var hash = window.location.hash.substring(1);' in resp

    def test_invalid_file(self):
        self.app.get('/src/1/tree/READMEz', status=404)

    def test_diff(self):
        resp = self.app.get('/src/3/tree/README?diff=2')
        assert 'This is readme' in resp, resp.showbrowser()
        assert '+++' in resp, resp.showbrowser()

    def test_checkout_svn(self):
        self.app.post('/p/test/admin/src/set_checkout_url',
                      {"checkout_url": "badurl"})
        r = self.app.get('/p/test/admin/src/checkout_url')
        assert 'value="badurl"' not in r
        self.app.post('/p/test/admin/src/set_checkout_url',
                      {"checkout_url": ""})
        r = self.app.get('/p/test/admin/src/checkout_url')
        assert 'value="trunk"' not in r
        self.app.post('/p/test/admin/src/set_checkout_url',
                      {"checkout_url": "a"})
        r = self.app.get('/p/test/admin/src/checkout_url')
        assert 'value="a"' in r

    def test_log(self):
        r = self.app.get('/src/1/log/')
        assert 'Create readme' in r
        r = self.app.get('/src/2/log/?path=')
        assert "Create readme" in r
        assert "Add path" in r
        r = self.app.get('/src/2/log/?path=README')
        assert "Modify readme" not in r
        assert "Create readme" in r
        r = self.app.get('/src/2/log/?path=/a/b/c/')
        assert 'Add path' in r
        assert 'Remove hello.txt' not in r
        r = self.app.get('/src/5/log/?path=a/b/c/')
        assert 'Add path' in r
        assert 'Remove hello.txt' in r
        r = self.app.get('/src/2/log/?path=does/not/exist/')
        assert 'No (more) commits' in r

    @skipUnless(os.path.exists(tg.config.get('scm.repos.tarball.zip_binary', '/usr/bin/zip')), 'zip binary is missing')
    def test_tarball(self):
        r = self.app.get('/src/3/tree/')
        assert 'Download Snapshot' in r
        r = self.app.post('/src/3/tarball').follow()
        assert 'Generating snapshot...' in r
        r = self.app.get('/src/3/tarball')
        assert 'Generating snapshot...' in r
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        r = self.app.get('/src/3/tarball_status')
        assert '{"status": "complete"}' in r
        r = self.app.get('/src/3/tarball')
        assert 'Your download will begin shortly' in r

    @skipUnless(os.path.exists(tg.config.get('scm.repos.tarball.zip_binary', '/usr/bin/zip')), 'zip binary is missing')
    def test_tarball_cyrillic(self):
        r = self.app.get('/src/6/tree/')
        assert 'Download Snapshot' in r
        r = self.app.post('/src/6/tarball').follow()
        assert 'Generating snapshot...' in r
        r = self.app.get('/src/6/tarball')
        assert 'Generating snapshot...' in r
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        r = self.app.get('/src/6/tarball_status')
        assert '{"status": "complete"}' in r
        r = self.app.get('/src/6/tarball')
        assert 'Your download will begin shortly' in r

    @skipUnless(os.path.exists(tg.config.get('scm.repos.tarball.zip_binary', '/usr/bin/zip')), 'zip binary is missing')
    def test_tarball_path(self):
        h.set_context('test', 'svn-tags', neighborhood='Projects')
        shutil.rmtree(c.app.repo.tarball_path, ignore_errors=True)
        r = self.app.get('/p/test/svn-tags/19/tree/')
        form = r.html.find('form', 'tarball')
        assert form.button.text == '\xa0Download Snapshot'
        assert form.get('action') == '/p/test/svn-tags/19/tarball'

        r = self.app.get('/p/test/svn-tags/19/tree/tags/tag-1.0/')
        form = r.html.find('form', 'tarball')
        assert form.button.text == '\xa0Download Snapshot'
        assert form.get('action') == '/p/test/svn-tags/19/tarball'
        assert form.find('input', attrs=dict(name='path')).get('value') == '/tags/tag-1.0'

        r = self.app.get('/p/test/svn-tags/19/tarball_status?path=/tags/tag-1.0')
        assert r.json['status'] is None
        r = self.app.post('/p/test/svn-tags/19/tarball',
                          dict(path='/tags/tag-1.0')).follow()
        assert 'Generating snapshot...' in r
        M.MonQTask.run_ready()
        r = self.app.get('/p/test/svn-tags/19/tarball_status?path=/tags/tag-1.0')
        assert r.json['status'] == 'complete'

        r = self.app.get('/p/test/svn-tags/19/tarball_status?path=/trunk')
        assert r.json['status'] is None
        r = self.app.post('/p/test/svn-tags/19/tarball',
                          dict(path='/trunk/')).follow()
        assert 'Generating snapshot...' in r
        M.MonQTask.run_ready()
        r = self.app.get('/p/test/svn-tags/19/tarball_status?path=/trunk')
        assert r.json['status'] == 'complete'

        r = self.app.get('/p/test/svn-tags/19/tarball_status?path=/branches/aaa/')
        assert r.json['status'] is None

        # this is is the same as trunk snapshot, so it's ready already
        r = self.app.get('/p/test/svn-tags/19/tarball_status')
        assert r.json['status'] == 'complete'


class TestImportController(SVNTestController):

    def test_index(self):
        r = self.app.get('/p/test/admin/src/importer').follow(status=200)
        assert 'You cannot import into a repository that already has commits in it.' in r

    @patch('forgesvn.svn_main.allura.tasks.repo_tasks')
    def test_do_import(self, tasks):
        self.app.post('/p/test/admin/src/importer/do_import',
                      {'checkout_url': 'http://fake.svn/'})
        assert not tasks.reclone.post.called

    @with_tool('test', 'SVN', 'empty', 'empty SVN')
    def test_index_empty_repo(self):
        r = self.app.get('/p/test/admin/empty/importer').follow(status=200)
        assert 'Enter the URL of the source repository below' in r

    @patch('forgesvn.svn_main.allura.tasks.repo_tasks')
    @with_tool('test', 'SVN', 'empty', 'empty SVN')
    def test_do_import_empty_repo(self, tasks):
        self.app.post('/p/test/admin/empty/importer/do_import',
                      {'checkout_url': 'http://github.com/'})
        assert tasks.reclone.post.called

    @patch('forgesvn.svn_main.allura.tasks.repo_tasks')
    @with_tool('test', 'SVN', 'empty', 'empty SVN')
    def test_validator(self, tasks):
        r = self.app.post('/p/test/admin/empty/importer/do_import',
                          {'checkout_url': 'http://10.0.0.0/trac/url'})
        assert 'Invalid URL' in r

        r = self.app.post('/p/test/admin/empty/importer/do_import',
                          {'checkout_url': 'http://fake.svn/'})
        assert 'That is not a valid URL' not in r

        r = self.app.post('/p/test/admin/empty/importer/do_import',
                          {'checkout_url': 'http://1.1.1.1'})
        assert 'That is not a valid URL' not in r

        r = self.app.post('/p/test/admin/empty/importer/do_import',
                          {'checkout_url': 'http://1.1.1'})
        assert 'That is not a valid URL' in r

        r = self.app.post('/p/test/admin/empty/importer/do_import',
                          {'checkout_url': 'http://256.200.200.200'})
        assert 'That is not a valid URL' in r

        r = self.app.post('/p/test/admin/empty/importer/do_import',
                          {'checkout_url': 'http://fak#e.svn/'})
        assert 'That is not a valid URL' in r


class SVNTestRenames(TestController):

    def setup_method(self, method):
        super().setup_method(method)
        self.setup_with_tools()

    @with_svn
    def setup_with_tools(self):
        h.set_context('test', 'src', neighborhood='Projects')
        repo_dir = pkg_resources.resource_filename(
            'forgesvn', 'tests/data/')
        c.app.repo.fs_path = repo_dir
        c.app.repo.status = 'ready'
        c.app.repo.name = 'testsvn'
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        h.set_context('test', 'src', neighborhood='Projects')
        c.app.repo.refresh()
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        h.set_context('test', 'src', neighborhood='Projects')

    def test_log(self):
        r = self.app.get('/src/3/log/?path=/dir/b.txt')
        assert '<b>renamed from</b>' in r
        assert '/dir/a.txt' in r
