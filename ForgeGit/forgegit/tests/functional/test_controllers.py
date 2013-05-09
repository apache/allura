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
import re
import os
import shutil

from nose.tools import assert_equal
import tg
import pkg_resources
from pylons import tmpl_context as c
from ming.orm import ThreadLocalORMSession
from datadiff.tools import assert_equal

from allura import model as M
from allura.lib import helpers as h
from alluratest.controller import TestController
from allura.tests.decorators import with_tool
from forgegit.tests import with_git

class _TestCase(TestController):

    def setUp(self):
        super(_TestCase, self).setUp()
        self.setup_with_tools()

    @with_git
    def setup_with_tools(self):
        h.set_context('test', 'src-git', neighborhood='Projects')
        repo_dir = pkg_resources.resource_filename(
            'forgegit', 'tests/data')
        c.app.repo.fs_path = repo_dir
        c.app.repo.status = 'ready'
        c.app.repo.name = 'testgit.git'
        ThreadLocalORMSession.flush_all()
        # ThreadLocalORMSession.close_all()
        h.set_context('test', 'src-git', neighborhood='Projects')
        c.app.repo.refresh()
        ThreadLocalORMSession.flush_all()
        # ThreadLocalORMSession.close_all()

    @with_tool('test', 'Git', 'testgit-index', 'Git', type='git')
    def setup_testgit_index_repo(self):
        h.set_context('test', 'testgit-index', neighborhood='Projects')
        repo_dir = pkg_resources.resource_filename(
            'forgegit', 'tests/data')
        c.app.repo.fs_path = repo_dir
        c.app.repo.status = 'ready'
        c.app.repo.name = 'testgit_index.git'
        ThreadLocalORMSession.flush_all()
        h.set_context('test', 'testgit-index', neighborhood='Projects')
        c.app.repo.refresh()
        ThreadLocalORMSession.flush_all()


class TestRootController(_TestCase):

    def test_status(self):
        resp = self.app.get('/src-git/status')
        d = json.loads(resp.body)
        assert d == dict(status='ready')

    def test_status_html(self):
        resp = self.app.get('/src-git/').follow().follow()
        # repo status not displayed if 'ready'
        assert None == resp.html.find('div', dict(id='repo_status'))
        h.set_context('test', 'src-git', neighborhood='Projects')
        c.app.repo.status = 'analyzing'
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        # repo status displayed if not 'ready'
        resp = self.app.get('/src-git/').follow().follow()
        div = resp.html.find('div', dict(id='repo_status'))
        assert div.span.text == 'analyzing'

    def test_index(self):
        resp = self.app.get('/src-git/').follow().follow()
        assert 'git://' in resp

    def test_index_empty(self):
        self.app.get('/git/')

    def test_commit_browser(self):
        resp = self.app.get('/src-git/commit_browser')

    def test_commit_browser_data(self):
        resp = self.app.get('/src-git/commit_browser_data')
        data = json.loads(resp.body);
        assert data['max_row'] == 4
        assert data['next_column'] == 1
        assert_equal(data['built_tree']['df30427c488aeab84b2352bdf88a3b19223f9d7a'],
                {u'url': u'/p/test/src-git/ci/df30427c488aeab84b2352bdf88a3b19223f9d7a/',
                 u'oid': u'df30427c488aeab84b2352bdf88a3b19223f9d7a',
                 u'column': 0,
                 u'parents': [u'6a45885ae7347f1cac5103b0050cc1be6a1496c8'],
                 u'message': u'Add README', u'row': 2})

    def test_log(self):
        resp = self.app.get('/src-git/ci/1e146e67985dcd71c74de79613719bef7bddca4a/log/')
        assert 'Initial commit' in resp
        assert '<div class="markdown_content"><p>Change README</p></div>' in resp
        assert 'tree/README?format=raw">Download</a>' not in resp
        assert '28 Bytes' not in resp.html.find('td').contents[1].text
        assert 'Tree' in resp.html.findAll('td')[2].text, resp.html.findAll('td')[2].text
        resp = self.app.get('/src-git/ci/1e146e67985dcd71c74de79613719bef7bddca4a/log/?path=/README')
        assert '28 Bytes' in resp.html.find('td').contents[1].text
        assert 'View' in resp.html.findAll('td')[2].text
        assert 'Change README' in resp
        assert 'tree/README?format=raw">Download</a>' in resp
        assert 'Add README' in resp
        assert "Initial commit " not in resp
        resp = self.app.get('/src-git/ci/1e146e67985dcd71c74de79613719bef7bddca4a/log/?path=/a/b/c/')
        assert 'Remove file' in resp
        assert 'Initial commit' in resp
        assert 'Add README' not in resp
        assert 'Change README' not in resp
        resp = self.app.get('/src-git/ci/1e146e67985dcd71c74de79613719bef7bddca4a/log/?path=/not/exist')
        assert 'No (more) commits' in resp

    def test_diff_ui(self):
        r = self.app.get('/src-git/ci/1e146e67985dcd71c74de79613719bef7bddca4a/log/?path=/README')
        assert '<div class="grid-19"><input type="button" value="Compare" class="compare_revision"></div>' in r
        assert '<input type="checkbox" class="revision"' in r
        assert 'revision="1e146e67985dcd71c74de79613719bef7bddca4a"' in r
        assert 'url_commit="/p/test/src-git/ci/1e146e67985dcd71c74de79613719bef7bddca4a/">' in r

        r = self.app.get('/src-git/ci/1e146e67985dcd71c74de79613719bef7bddca4a/log/')
        assert '<div class="grid-19"><input type="button" value="Compare" class="compare_revision"></div>' not in r
        assert '<input type="checkbox" class="revision"' not in r
        assert 'revision="1e146e67985dcd71c74de79613719bef7bddca4a"' not in r
        assert 'url_commit="/p/test/src-git/ci/1e146e67985dcd71c74de79613719bef7bddca4a/">' not in r

    def test_tags(self):
        resp = self.app.get('/src-git/ref/master~/tags/')

    def _get_ci(self):
        r = self.app.get('/src-git/ref/master/')
        resp = r.follow()
        for tag in resp.html.findAll('a'):
            if tag['href'].startswith('/p/test/src-git/ci/'):
                href = tag['href']
                if href.endswith('tree/'):
                    href = href[:-5]
                return href
        return None

    def test_commit(self):
        ci = self._get_ci()
        resp = self.app.get(ci)
        assert 'Rick' in resp, resp.showbrowser()

    def test_feed(self):
        for ext in ['', '.rss', '.atom']:
            assert 'Add README' in self.app.get('/feed%s' % ext)

    def test_tree(self):
        ci = self._get_ci()
        resp = self.app.get(ci + 'tree/')
        assert len(resp.html.findAll('tr')) == 2, resp.showbrowser()
        resp = self.app.get(ci + 'tree/')
        assert 'README' in resp, resp.showbrowser()
        links = [ a.get('href') for a in resp.html.findAll('a') ]
        assert 'README' in links, resp.showbrowser()
        assert 'README/' not in links, resp.showbrowser()

    def test_tree_extra_params(self):
        ci = self._get_ci()
        resp = self.app.get(ci + 'tree/?format=raw')
        assert 'README' in resp, resp.showbrowser()

    def test_file(self):
        ci = self._get_ci()
        resp = self.app.get(ci + 'tree/README')
        assert 'README' in resp.html.find('h2', {'class':'dark title'}).contents[2]
        content = str(resp.html.find('div', {'class':'clip grid-19 codebrowser'}))
        assert 'This is readme' in content, content
        assert '<span id="l1" class="code_block">' in resp
        assert 'var hash = window.location.hash.substring(1);' in resp

    def test_invalid_file(self):
        ci = self._get_ci()
        self.app.get(ci + 'tree/READMEz', status=404)

    def test_diff(self):
        ci = self._get_ci()
        resp = self.app.get(ci + 'tree/README?diff=df30427c488aeab84b2352bdf88a3b19223f9d7a')
        assert 'readme' in resp, resp.showbrowser()
        assert '+++' in resp, resp.showbrowser()

    def test_diff_view_mode(self):
        ci = self._get_ci()
        fn = 'tree/README?diff=df30427c488aeab84b2352bdf88a3b19223f9d7a'
        r = self.app.get(ci + fn + '&diformat=regular')
        assert fn + '&amp;diformat=sidebyside">Switch to side-by-side view</a>' in r

        r = self.app.get(ci + fn + '&diformat=sidebyside')
        assert fn + '&amp;diformat=regular">Switch to unified view</a>' in r
        assert '<table class="side-by-side-diff">' in r

    def test_refresh(self):
        notification = M.Notification.query.find(
            dict(subject='[test:src-git] 5 new commits to test Git')).first()
        domain = '.'.join(reversed(c.app.url[1:-1].split('/'))).replace('_', '-')
        common_suffix = tg.config.get('forgemail.domain', '.sourceforge.net')
        email = 'noreply@%s%s' % (domain, common_suffix)
        assert email in notification['reply_to_address']

    def test_file_force_display(self):
        ci = self._get_ci()
        resp = self.app.get(ci + 'tree/README?force=True')
        content = str(resp.html.find('div', {'class':'clip grid-19 codebrowser'}))
        assert re.search(r'<pre>.*This is readme', content), content
        assert '</pre>' in content, content

    def test_index_files(self):
        """Test that `index.*` files are viewable in code browser"""
        self.setup_testgit_index_repo()
        ci = '/p/test/testgit-index/ci/eaec8e7fc91f18d6bf294379d16146ef9226a1ab/'

        # `index.html` in repo root
        r = self.app.get(ci + 'tree/index.html')
        header = r.html.find('h2', {'class': 'dark title'}).contents[2]
        assert 'index.html' in header, header
        content = str(r.html.find('div', {'class': 'clip grid-19 codebrowser'}))
        assert ('<span class="nt">&lt;h1&gt;</span>'
                'index.html'
                '<span class="nt">&lt;/h1&gt;</span>') in content, content

        # `index` dir in repo root
        r = self.app.get(ci + 'tree/index/')
        assert 'inside_index_dir.txt' in r

        # `index.htm` in `index` dir
        r = self.app.get(ci + 'tree/index/index.htm')
        header = r.html.find('h2', {'class': 'dark title'})
        assert 'index' in header.contents[3], header.contents[3]
        assert 'index.htm' in header.contents[4], header.contents[4]
        content = str(r.html.find('div', {'class': 'clip grid-19 codebrowser'}))
        assert ('<span class="nt">&lt;h1&gt;</span>'
                'index/index.htm'
                '<span class="nt">&lt;/h1&gt;</span>') in content, content

    def test_subscribe(self):
        user = M.User.query.get(username='test-user')
        ci = self._get_ci()

        # user is not subscribed
        assert not M.Mailbox.subscribed(user_id=user._id)
        r = self.app.get(ci + 'tree/',
                extra_environ={'username': str(user.username)})
        header = r.html.find('h2', {'class': 'dark title'})
        link = header.find('a', {'class': 'artifact_subscribe'})
        assert link is not None, header

        # subscribe
        self.app.get(ci + 'tree/subscribe?subscribe=True',
                extra_environ={'username': str(user.username)}).follow()
        # user is subscribed
        assert M.Mailbox.subscribed(user_id=user._id)
        r = self.app.get(ci + 'tree/',
                extra_environ={'username': str(user.username)})
        header = r.html.find('h2', {'class': 'dark title'})
        link = header.find('a', {'class': 'artifact_unsubscribe active'})
        assert link is not None, header

        # unsubscribe
        self.app.get(ci + 'tree/subscribe?unsubscribe=True',
                extra_environ={'username': str(user.username)}).follow()
        # user is not subscribed
        assert not M.Mailbox.subscribed(user_id=user._id)
        r = self.app.get(ci + 'tree/',
                extra_environ={'username': str(user.username)})
        header = r.html.find('h2', {'class': 'dark title'})
        link = header.find('a', {'class': 'artifact_subscribe'})
        assert link is not None, header

    def test_timezone(self):
        ci = self._get_ci()
        resp = self.app.get(ci + 'tree/')
        assert "Thu Oct 07, 2010 06:44 PM UTC" in resp, resp.showbrowser()

    def test_checkout_input(self):
        ci = self._get_ci()
        r = self.app.get('/src-git/commit_browser')
        assert not '<div id="access_urls"' in r
        r = self.app.get('/src-git/fork')
        assert not '<div id="access_urls"' in r
        r = self.app.get(
            ci +
            'tree/README?diff=df30427c488aeab84b2352bdf88a3b19223f9d7a')
        assert not '<div id="access_urls"' in r
        r = self.app.get(ci + 'tree/README')
        assert not '<div id="access_urls"' in r
        r = self.app.get(ci + 'tree/')
        assert '<div id="access_urls"' in r

    def test_tarball(self):
        ci = self._get_ci()
        r = self.app.get(ci + 'tree/')
        assert 'Download Snapshot' in r
        r = self.app.get(ci + 'tarball')
        assert 'Generating snapshot...' in r
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        r = self.app.get(ci + 'tarball_status')
        assert '{"status": "ready"}' in r


class TestRestController(_TestCase):

    def test_index(self):
        self.app.get('/rest/p/test/src-git/', status=200)

    def test_commits(self):
        self.app.get('/rest/p/test/src-git/commits', status=200)

class TestFork(_TestCase):

    def setUp(self):
        super(TestFork, self).setUp()
        to_project = M.Project.query.get(
            shortname='test2', neighborhood_id=c.project.neighborhood_id)
        r = self.app.post('/src-git/fork', params=dict(
                project_id=str(to_project._id),
                mount_point='code',
                mount_label='Test forked repository'))
        assert "{status: 'error'}" not in str(r.follow())
        cloned_from = c.app.repo
        with h.push_context('test2', 'code', neighborhood='Projects'):
            c.app.repo.init_as_clone(
                    cloned_from.full_fs_path,
                    cloned_from.app.config.script_name(),
                    cloned_from.full_fs_path)
            # Add commit to a forked repo, thus merge requests will not be empty
            # clone repo to tmp location first (can't add commit to bare repos directly)
            clone_path = '/tmp/test2-code-clone'
            if os.path.exists(clone_path):
                shutil.rmtree(clone_path)
            cloned = c.app.repo._impl._git.clone(clone_path)
            with open(clone_path + '/README', 'w+') as f:
                f.write('Very useful README')
            cloned.index.add(['README'])
            cloned.index.commit('Improve documentation')
            cloned.remotes[0].push()
            c.app.repo.refresh()
            self.forked_repo = c.app.repo

    def _follow(self, r, **kw):
        if r.status_int == 302:
            print r.request.url
        while r.status_int == 302:
            print ' ==> 302 ==> %s' % r.location
            r = r.follow(**kw)
        return r

    def _upstream_page(self, **kw):
        r = self.app.get('/src-git/', **kw)
        r = self._follow(r, **kw)
        return r

    def _fork_page(self, **kw):
        r = self.app.get('/p/test2/code/', **kw)
        r = self._follow(r, **kw)
        return r

    def _request_merge(self, **kw):
        r = self.app.get('/p/test2/code/request_merge', **kw)
        r = self._follow(r, **kw)
        r = r.forms[0].submit()
        r = self._follow(r, **kw)
        mr_num = r.request.url.split('/')[-2]
        assert mr_num.isdigit(), mr_num
        return r, mr_num

    def test_forks_list(self):
        r = self.app.get('%sforks/' % c.app.repo.url())
        assert 'test2 / code' in r

    def test_fork_form(self):
        r = self.app.get('%sfork/' % c.app.repo.url())
        assert '<input type="text" name="mount_point" value="test"/>' in r
        assert '<input type="text" name="mount_label" value="test - Git"/>' in r

    def test_fork_listed_in_parent(self):
        assert 'Forks' in self._upstream_page()

    def test_fork_display(self):
        r = self._fork_page()
        assert 'Clone of' in r
        assert 'Test forked repository' in r

    def test_fork_links_go_to_fork(self):
        r = self._fork_page()
        hrefs = ( a.get('href') for a in r.html('a') )
        hrefs = ( href for href in hrefs if href and '/ci/' in href )
        for href in hrefs:
            assert href.startswith('/p/test2/code/'), href

    def test_merge_request_visible_to_admin(self):
        assert 'Request Merge' in self._fork_page()

    def test_merge_request_invisible_to_non_admin(self):
        assert 'Request Merge' not in self._fork_page(
            extra_environ=dict(username='test-user'))

    def test_merge_action_available_to_admin(self):
        self.app.get('/p/test2/code/request_merge')

    def test_merge_action_unavailable_to_non_admin(self):
        self.app.get(
            '/p/test2/code/request_merge',
            status=403, extra_environ=dict(username='test-user'))

    def test_merge_request_detail_view(self):
        r, mr_num = self._request_merge()
        assert 'would like you to merge' in r, r.showbrowser()
        assert 'Improve documentation' in r, r.showbrowser()
        revs = r.html.findAll('tr', attrs={'class': 'rev'})
        links = revs[0].findAll('a')
        c_id = self.forked_repo.heads[0]['object_id']
        assert_equal(links[0].get('href'), '/p/test2/code/ci/%s/' % c_id)
        assert_equal(links[0].getText(), '[%s]' % c_id[:6])
        assert_equal(links[1].get('href'), '/p/test2/code/ci/%s/tree' % c_id)
        assert_equal(links[1].getText(), 'Tree')

    def test_merge_request_list_view(self):
        r, mr_num = self._request_merge()
        r = self.app.get('/p/test/src-git/merge-requests/')
        assert 'href="%s/"' % mr_num in r, r

    def test_merge_request_update_status(self):
        r, mr_num = self._request_merge()
        r = self.app.post('/p/test/src-git/merge-requests/%s/save' % mr_num,
                          params=dict(status='rejected')).follow()
        assert 'Merge Request #%s:  (rejected)' % mr_num in r, r

class TestDiff(TestController):

    def setUp(self):
        super(TestDiff, self).setUp()
        self.setup_with_tools()

    @with_git
    def setup_with_tools(self):
        h.set_context('test', 'src-git', neighborhood='Projects')
        repo_dir = pkg_resources.resource_filename(
            'forgegit', 'tests/data')
        c.app.repo.fs_path = repo_dir
        c.app.repo.status = 'ready'
        c.app.repo.name = 'testmime.git'
        ThreadLocalORMSession.flush_all()
        h.set_context('test', 'src-git', neighborhood='Projects')
        c.app.repo.refresh()
        ThreadLocalORMSession.flush_all()

    def test_diff(self):
        r = self.app.get('/src-git/ci/d961abbbf10341ee18a668c975842c35cfc0bef2/tree/1.png?barediff=2ce83a24e52c21e8d2146b1a04a20717c0bb08d7')
        assert 'alt="2ce83a2..."' in r
        assert 'alt="d961abb..."' in r

        r = self.app.get('/src-git/ci/d961abbbf10341ee18a668c975842c35cfc0bef2/tree/1.png?diff=2ce83a24e52c21e8d2146b1a04a20717c0bb08d7')
        assert 'alt="2ce83a2..."' in r
        assert 'alt="d961abb..."' in r

