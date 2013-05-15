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

import os
import shutil
import stat
import unittest
import pkg_resources
import datetime

import mock
from pylons import tmpl_context as c, app_globals as g
import tg
from ming.base import Object
from ming.orm import ThreadLocalORMSession, session
from nose.tools import assert_equal
from testfixtures import TempDirectory

from alluratest.controller import setup_basic_test, setup_global_objects
from allura.lib import helpers as h
from allura.tests import decorators as td
from allura.tests.model.test_repo import RepoImplTestBase
from allura import model as M
from allura.model.repo_refresh import send_notifications
from forgegit import model as GM
from forgegit.tests import with_git
from forgewiki import model as WM

class TestNewGit(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        self.setup_with_tools()

    @with_git
    @td.with_wiki
    def setup_with_tools(self):
        setup_global_objects()
        h.set_context('test', 'src-git', neighborhood='Projects')
        repo_dir = pkg_resources.resource_filename(
            'forgegit', 'tests/data')
        c.app.repo.fs_path = repo_dir
        c.app.repo.name = 'testgit.git'
        self.repo = c.app.repo
        #self.repo = GM.Repository(
        #     name='testgit.git',
        #     fs_path=repo_dir,
        #     url_path = '/test/',
        #     tool = 'git',
        #     status = 'creating')
        self.repo.refresh()
        self.rev = M.repo.Commit.query.get(_id=self.repo.heads[0]['object_id'])
        self.rev.repo = self.repo
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_commit(self):
        assert self.rev.primary() is self.rev
        assert self.rev.index_id().startswith('allura/model/repo/Commit#')
        self.rev.author_url
        self.rev.committer_url
        assert self.rev.tree._id == self.rev.tree_id
        assert self.rev.summary == self.rev.message.splitlines()[0]
        assert self.rev.shorthand_id() == '[1e146e]'
        assert self.rev.symbolic_ids == (['master', 'zz'], [])
        assert self.rev.url() == (
            '/p/test/src-git/ci/'
            '1e146e67985dcd71c74de79613719bef7bddca4a/')
        all_cis = self.repo.log(self.rev._id, 0, 1000)
        assert len(all_cis) == 4
        assert_equal(self.repo.log(self.rev._id, 1,1000), all_cis[1:])
        assert_equal(self.repo.log(self.rev._id, 0,3), all_cis[:3])
        assert_equal(self.repo.log(self.rev._id, 1,2), all_cis[1:3])
        for ci in all_cis:
            ci.context()
        self.rev.tree.ls()
        # print self.rev.tree.readme()
        assert_equal(self.rev.tree.readme(), (
            'README', 'This is readme\nAnother Line\n'))
        assert self.rev.tree.path() == '/'
        assert self.rev.tree.url() == (
            '/p/test/src-git/ci/'
            '1e146e67985dcd71c74de79613719bef7bddca4a/'
            'tree/')
        self.rev.tree.by_name['README']
        assert self.rev.tree.is_blob('README') == True
        ThreadLocalORMSession.close_all()
        c.app = None
        converted = g.markdown.convert('[1e146e]')
        assert '1e146e' in converted, converted
        h.set_context('test', 'wiki', neighborhood='Projects')
        pg = WM.Page(
            title='Test Page', text='This is a commit reference: [1e146e]')
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        for ci in pg.related_artifacts():
            assert ci.shorthand_id() == '[1e146e]', ci.shorthand_id()
            assert ci.url() == (
                '/p/test/src-git/ci/'
                '1e146e67985dcd71c74de79613719bef7bddca4a/')

class TestGitRepo(unittest.TestCase, RepoImplTestBase):

    def setUp(self):
        setup_basic_test()
        self.setup_with_tools()

    @with_git
    def setup_with_tools(self):
        setup_global_objects()
        h.set_context('test', 'src-git', neighborhood='Projects')
        repo_dir = pkg_resources.resource_filename(
            'forgegit', 'tests/data')
        self.repo = GM.Repository(
            name='testgit.git',
            fs_path=repo_dir,
            url_path = '/test/',
            tool = 'git',
            status = 'creating')
        self.repo.refresh()
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_init(self):
        repo = GM.Repository(
            name='testgit.git',
            fs_path=g.tmpdir+'/',
            url_path = '/test/',
            tool = 'git',
            status = 'creating')
        dirname = os.path.join(repo.fs_path, repo.name)
        if os.path.exists(dirname):
            shutil.rmtree(dirname)
        repo.init()
        shutil.rmtree(dirname)

    def test_fork(self):
        repo = GM.Repository(
            name='testgit.git',
            fs_path=g.tmpdir + '/',
            url_path = '/test/',
            tool = 'git',
            status = 'creating')
        repo_path = pkg_resources.resource_filename(
            'forgegit', 'tests/data/testgit.git')
        dirname = os.path.join(repo.fs_path, repo.name)
        if os.path.exists(dirname):
            shutil.rmtree(dirname)
        repo.init()
        repo._impl.clone_from(repo_path)
        assert not os.path.exists(os.path.join(g.tmpdir, 'testgit.git/hooks/update'))
        assert not os.path.exists(os.path.join(g.tmpdir, 'testgit.git/hooks/post-receive-user'))
        assert os.path.exists(os.path.join(g.tmpdir, 'testgit.git/hooks/post-receive'))
        assert os.stat(os.path.join(g.tmpdir, 'testgit.git/hooks/post-receive'))[0] & stat.S_IXUSR

    @mock.patch('forgegit.model.git_repo.g.post_event')
    def test_clone(self, post_event):
        repo = GM.Repository(
            name='testgit.git',
            fs_path=g.tmpdir + '/',
            url_path = '/test/',
            tool = 'git',
            status = 'creating')
        repo_path = pkg_resources.resource_filename(
            'forgegit', 'tests/data/testgit.git')
        dirname = os.path.join(repo.fs_path, repo.name)
        if os.path.exists(dirname):
            shutil.rmtree(dirname)
        repo.init()
        repo._impl.clone_from(repo_path)
        assert len(repo.log())
        assert not os.path.exists(os.path.join(g.tmpdir, 'testgit.git/hooks/update'))
        assert not os.path.exists(os.path.join(g.tmpdir, 'testgit.git/hooks/post-receive-user'))
        assert os.path.exists(os.path.join(g.tmpdir, 'testgit.git/hooks/post-receive'))
        assert os.stat(os.path.join(g.tmpdir, 'testgit.git/hooks/post-receive'))[0] & stat.S_IXUSR
        with open(os.path.join(g.tmpdir, 'testgit.git/hooks/post-receive')) as f: c = f.read()
        self.assertIn('curl -s http://localhost//auth/refresh_repo/p/test/src-git/\n', c)
        self.assertIn('exec $DIR/post-receive-user\n', c)
        shutil.rmtree(dirname)

    @mock.patch('forgegit.model.git_repo.git.Repo.clone_from')
    @mock.patch('forgegit.model.git_repo.g.post_event')
    def test_hotcopy(self, post_event, clone_from):
        with h.push_config(tg.config, **{'scm.git.hotcopy': 'True'}):
            repo = GM.Repository(
                name='testgit.git',
                fs_path=g.tmpdir+'/',
                url_path = '/test/',
                tool = 'git',
                status = 'creating')
            repo.app.config.options['hotcopy'] = True
            repo_path = pkg_resources.resource_filename(
                'forgegit', 'tests/data/testgit.git')
            dirname = os.path.join(repo.fs_path, repo.name)
            if os.path.exists(dirname):
                shutil.rmtree(dirname)
            repo.init()
            repo._impl.clone_from(repo_path)
            assert not clone_from.called
            assert len(repo.log())
            assert os.path.exists(os.path.join(g.tmpdir, 'testgit.git/hooks/update'))
            assert os.path.exists(os.path.join(g.tmpdir, 'testgit.git/hooks/post-receive-user'))
            assert os.path.exists(os.path.join(g.tmpdir, 'testgit.git/hooks/post-receive'))
            assert os.stat(os.path.join(g.tmpdir, 'testgit.git/hooks/post-receive'))[0] & stat.S_IXUSR
            with open(os.path.join(g.tmpdir, 'testgit.git/hooks/post-receive')) as f: c = f.read()
            self.assertIn('curl -s http://localhost//auth/refresh_repo/p/test/src-git/\n', c)
            self.assertIn('exec $DIR/post-receive-user\n', c)
            shutil.rmtree(dirname)

    def test_index(self):
        i = self.repo.index()
        assert i['type_s'] == 'Git Repository', i

    def test_log(self):
        for entry in self.repo.log():
            assert str(entry.authored)
            assert entry.message

    def test_commit(self):
        entry = self.repo.commit('HEAD')
        assert str(entry.authored.name) == 'Rick Copeland', entry.authored
        assert entry.message
        # Test that sha1s for named refs are looked up in cache first, instead
        # of from disk.
        with mock.patch('forgegit.model.git_repo.M.repo.Commit.query') as q:
            self.repo.heads.append(Object(name='HEAD', object_id='deadbeef'))
            self.repo.commit('HEAD')
            q.get.assert_called_with(_id='deadbeef')
        # test the auto-gen tree fall-through
        orig_tree = M.repo.Tree.query.get(_id=entry.tree_id)
        assert orig_tree
        # force it to regenerate the tree
        M.repo.Tree.query.remove(dict(_id=entry.tree_id))
        session(orig_tree).flush()
        # ensure we don't just pull it from the session cache
        session(orig_tree).expunge(orig_tree)
        # ensure we don't just use the LazyProperty copy
        session(entry).expunge(entry)
        entry = self.repo.commit(entry._id)
        # regenerate the tree
        new_tree = entry.tree
        assert new_tree
        self.assertEqual(new_tree._id, orig_tree._id)
        self.assertEqual(new_tree.tree_ids, orig_tree.tree_ids)
        self.assertEqual(new_tree.blob_ids, orig_tree.blob_ids)
        self.assertEqual(new_tree.other_ids, orig_tree.other_ids)

    def test_notification_email(self):
        send_notifications(self.repo, ['1e146e67985dcd71c74de79613719bef7bddca4a', ])
        ThreadLocalORMSession.flush_all()
        notifications = M.Notification.query.find().sort('pubdate')
        n = notifications.all()[2]
        assert_equal(n.subject, '[test:src-git] Rick Copeland committed revision 1e146e67985dcd71c74de79613719bef7bddca4a: Change README')
        assert 'master,zz: ' in n.text
        send_notifications(self.repo, ['1e146e67985dcd71c74de79613719bef7bddca4a', 'df30427c488aeab84b2352bdf88a3b19223f9d7a'])
        ThreadLocalORMSession.flush_all()
        notifications = M.Notification.query.find().sort('pubdate')
        n = notifications.all()[3]
        assert_equal(n.subject, '[test:src-git] 2 new commits to test Git')

    def test_tarball(self):
        tmpdir = tg.config['scm.repos.tarball.root']
        if os.path.isfile(os.path.join(tmpdir, "git/t/te/test/testgit.git/test-src-git-HEAD.zip")):
            os.remove(os.path.join(tmpdir, "git/t/te/test/testgit.git/test-src-git-HEAD.zip"))
        assert_equal(self.repo.tarball_path, os.path.join(tmpdir, 'git/t/te/test/testgit.git'))
        assert_equal(self.repo.tarball_url('HEAD'), 'file:///git/t/te/test/testgit.git/test-src-git-HEAD.zip')
        self.repo.tarball('HEAD')
        assert os.path.isfile(os.path.join(tmpdir, "git/t/te/test/testgit.git/test-src-git-HEAD.zip"))

    def test_all_commit_ids(self):
        cids = list(self.repo.all_commit_ids())
        heads = [
                '1e146e67985dcd71c74de79613719bef7bddca4a',  # master
                '5c47243c8e424136fd5cdd18cd94d34c66d1955c',  # zz
            ]
        self.assertIn(cids[0], heads)  # repo head comes first
        for head in heads:
            self.assertIn(head, cids)  # all branches included
        self.assertEqual(cids[-1], '9a7df788cf800241e3bb5a849c8870f2f8259d98')  # repo root comes last

    def test_ls(self):
        lcd_map = self.repo.commit('HEAD').tree.ls()
        self.assertEqual(lcd_map, [{
                'href': u'README',
                'kind': 'BLOB',
                'last_commit': {
                    'author': u'Rick Copeland',
                    'author_email': u'rcopeland@geek.net',
                    'author_url': None,
                    'date': datetime.datetime(2010, 10, 7, 18, 44, 11),
                    'href': u'/p/test/src-git/ci/1e146e67985dcd71c74de79613719bef7bddca4a/',
                    'shortlink': u'[1e146e]',
                    'summary': u'Change README'},
                'name': u'README'}])

    def test_tarball_status(self):
        tmpdir = tg.config['scm.repos.tarball.root']
        if os.path.isfile(os.path.join(tmpdir, "git/t/te/test/testgit.git/test-src-git-HEAD.zip")):
            os.remove(os.path.join(tmpdir, "git/t/te/test/testgit.git/test-src-git-HEAD.zip"))
        if os.path.isfile(os.path.join(tmpdir, "git/t/te/test/testgit.git/test-src-git-HEAD.tmp")):
            os.remove(os.path.join(tmpdir, "git/t/te/test/testgit.git/test-src-git-HEAD.tmp"))
        if os.path.isdir(os.path.join(tmpdir, "git/t/te/test/testgit.git/test-src-git-HEAD/")):
            os.removedirs(os.path.join(tmpdir, "git/t/te/test/testgit.git/test-src-git-HEAD/"))
        self.repo.tarball('HEAD')
        assert_equal(self.repo.get_tarball_status('HEAD'), 'ready')
        os.rename(os.path.join(tmpdir, "git/t/te/test/testgit.git/test-src-git-HEAD.zip"),
                  os.path.join(tmpdir, "git/t/te/test/testgit.git/test-src-git-HEAD.tmp"))
        assert_equal(self.repo.get_tarball_status('HEAD'), 'busy')
        os.remove(os.path.join(tmpdir, "git/t/te/test/testgit.git/test-src-git-HEAD.tmp"))
        assert_equal(self.repo.get_tarball_status('HEAD'), None)
        os.makedirs(os.path.join(tmpdir, "git/t/te/test/testgit.git/test-src-git-HEAD"))
        assert_equal(self.repo.get_tarball_status('HEAD'), None)

    def test_is_empty(self):
        assert not self.repo.is_empty()
        with TempDirectory() as d:
            repo2 = GM.Repository(
                name='test',
                fs_path=d.path,
                url_path = '/test/',
                tool = 'git',
                status = 'creating')
            repo2.init()
            assert repo2.is_empty()
            repo2.refresh()
            ThreadLocalORMSession.flush_all()
            assert repo2.is_empty()


class TestGitCommit(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        self.setup_with_tools()

    @with_git
    def setup_with_tools(self):
        setup_global_objects()
        h.set_context('test', 'src-git', neighborhood='Projects')
        repo_dir = pkg_resources.resource_filename(
            'forgegit', 'tests/data')
        self.repo = GM.Repository(
            name='testgit.git',
            fs_path=repo_dir,
            url_path = '/test/',
            tool = 'git',
            status = 'creating')
        self.repo.refresh()
        self.rev = self.repo.commit('HEAD')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_url(self):
        assert self.rev.url().endswith('ca4a/')
        assert self.repo._impl.url_for_commit('master').endswith('master/'), self.repo._impl.url_for_commit('master')

    def test_committer_url(self):
        assert self.rev.committer_url is None

    def test_primary(self):
        assert self.rev.primary() == self.rev

    def test_shorthand(self):
        assert len(self.rev.shorthand_id()) == 8

    def test_diff(self):
        diffs = (self.rev.diffs.added
                 +self.rev.diffs.removed
                 +self.rev.diffs.changed
                 +self.rev.diffs.copied)
        for d in diffs:
            print d

    def test_commits(self):
        # path only
        commits = list(self.repo.commits())
        assert len(commits) == 4, 'Returned %s commits' % len(commits)
        assert "9a7df788cf800241e3bb5a849c8870f2f8259d98" in commits, commits
        commits = list(self.repo.commits('README'))
        assert len(commits) == 2, 'Returned %s README commits' % len(commits)
        assert "1e146e67985dcd71c74de79613719bef7bddca4a" in commits, commits
        assert "df30427c488aeab84b2352bdf88a3b19223f9d7a" in commits, commits
        assert list(self.repo.commits('does/not/exist')) == []
        # with path and start rev
        commits = list(self.repo.commits('README', 'df30427c488aeab84b2352bdf88a3b19223f9d7a'))
        assert_equal(commits, ['df30427c488aeab84b2352bdf88a3b19223f9d7a'])
        # skip and limit
        commits = list(self.repo.commits(None, rev=None, skip=1, limit=2))
        assert_equal(commits, ['df30427c488aeab84b2352bdf88a3b19223f9d7a', '6a45885ae7347f1cac5103b0050cc1be6a1496c8'])
        commits = list(self.repo.commits(None, '6a45885ae7347f1cac5103b0050cc1be6a1496c8', skip=1))
        assert_equal(commits, ['9a7df788cf800241e3bb5a849c8870f2f8259d98'])
        commits = list(self.repo.commits('README', 'df30427c488aeab84b2352bdf88a3b19223f9d7a', skip=1))
        assert commits == []
        # path to dir
        commits = list(self.repo.commits('a/b/c/'))
        assert commits == ['6a45885ae7347f1cac5103b0050cc1be6a1496c8', '9a7df788cf800241e3bb5a849c8870f2f8259d98']
        commits = list(self.repo.commits('a/b/c/', skip=1))
        assert commits == ['9a7df788cf800241e3bb5a849c8870f2f8259d98']
        commits = list(self.repo.commits('a/b/c/', limit=1))
        assert commits == ['6a45885ae7347f1cac5103b0050cc1be6a1496c8']
        commits = list(self.repo.commits('not/exist/'))
        assert commits == []
        # with missing add record
        commit = M.repo.Commit.query.get(_id='df30427c488aeab84b2352bdf88a3b19223f9d7a')
        commit.changed_paths = []
        commits = list(self.repo.commits('README', 'df30427c488aeab84b2352bdf88a3b19223f9d7a'))
        assert_equal(commits, ['df30427c488aeab84b2352bdf88a3b19223f9d7a'])
        # with missing add record & no parent
        commit = M.repo.Commit.query.get(_id='9a7df788cf800241e3bb5a849c8870f2f8259d98')
        commit.changed_paths = ['a']
        commits = list(self.repo.commits('a/b/c/hello.txt', '9a7df788cf800241e3bb5a849c8870f2f8259d98'))
        assert_equal(commits, ['9a7df788cf800241e3bb5a849c8870f2f8259d98'])

    def test_commits_count(self):
        commits = self.repo.commits_count()
        assert commits == 4, commits
        commits = self.repo.commits_count('README')
        assert commits == 2, commits
        commits = self.repo.commits_count(None, 'df30427c488aeab84b2352bdf88a3b19223f9d7a')
        assert commits == 3, commits
        commits = self.repo.commits_count('a/b/c/hello.txt', '6a45885ae7347f1cac5103b0050cc1be6a1496c8')
        assert commits == 2, commits
        commits = self.repo.commits_count('a/b/c/')
        assert commits == 2, commits
        commits = self.repo.commits_count('not/exist/')
        assert commits == 0, commits


class TestGitHtmlView(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        self.setup_with_tools()

    @with_git
    def setup_with_tools(self):
        setup_global_objects()
        h.set_context('test', 'src-git', neighborhood='Projects')
        repo_dir = pkg_resources.resource_filename(
            'forgegit', 'tests/data')
        self.repo = GM.Repository(
            name='testmime.git',
            fs_path=repo_dir,
            url_path='/test/',
            tool='git',
            status='creating')
        self.repo.refresh()
        self.rev = self.repo.commit('HEAD')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_html_view(self):
        b = self.rev.tree.get_blob_by_path('README')
        assert b.has_html_view
        b = self.rev.tree.get_blob_by_path('test.jpg')
        assert not b.has_html_view
        b = self.rev.tree.get_blob_by_path('ChangeLog')
        assert b.has_html_view
        b = self.rev.tree.get_blob_by_path('test.spec.in')
        assert b.has_html_view
