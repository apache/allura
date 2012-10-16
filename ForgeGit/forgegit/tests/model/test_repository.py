import os
import shutil
import unittest
import pkg_resources

import mock
import pylons
pylons.c = pylons.tmpl_context
pylons.g = pylons.app_globals
from pylons import c, g
from ming.base import Object
from ming.orm import ThreadLocalORMSession, session
from nose.tools import assert_equal

from alluratest.controller import setup_basic_test, setup_global_objects
from allura.lib import helpers as h
from allura.tests import decorators as td
from allura.tests.model.test_repo import RepoImplTestBase
from allura import model as M
from forgegit import model as GM
from forgewiki import model as WM

class TestNewGit(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        self.setup_with_tools()

    @td.with_git
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
        assert self.rev.symbolic_ids == (['master'], [])
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

    @td.with_git
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
            fs_path='/tmp/',
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
            fs_path='/tmp/',
            url_path = '/test/',
            tool = 'git',
            status = 'creating')
        repo_path = pkg_resources.resource_filename(
            'forgegit', 'tests/data/testgit.git')
        dirname = os.path.join(repo.fs_path, repo.name)
        if os.path.exists(dirname):
            shutil.rmtree(dirname)
        repo.init()
        repo._impl.clone_from(repo_path, copy_hooks=False)
        assert not os.path.exists('/tmp/testgit.git/hooks/update')
        assert not os.path.exists('/tmp/testgit.git/hooks/post-receive-user')
        assert os.path.exists('/tmp/testgit.git/hooks/post-receive')
        assert os.access('/tmp/testgit.git/hooks/post-receive', os.X_OK)

    def test_clone(self):
        repo = GM.Repository(
            name='testgit.git',
            fs_path='/tmp/',
            url_path = '/test/',
            tool = 'git',
            status = 'creating')
        repo_path = pkg_resources.resource_filename(
            'forgegit', 'tests/data/testgit.git')
        dirname = os.path.join(repo.fs_path, repo.name)
        if os.path.exists(dirname):
            shutil.rmtree(dirname)
        repo.init()
        repo._impl.clone_from(repo_path, copy_hooks=True)
        assert len(repo.log())
        assert os.path.exists('/tmp/testgit.git/hooks/update')
        assert os.access('/tmp/testgit.git/hooks/update', os.X_OK)
        with open('/tmp/testgit.git/hooks/update') as f: c = f.read()
        self.assertEqual(c, 'update\n')
        assert os.path.exists('/tmp/testgit.git/hooks/post-receive-user')
        assert os.access('/tmp/testgit.git/hooks/post-receive-user', os.X_OK)
        with open('/tmp/testgit.git/hooks/post-receive-user') as f: c = f.read()
        self.assertEqual(c, 'post-receive\n')
        assert os.path.exists('/tmp/testgit.git/hooks/post-receive')
        assert os.access('/tmp/testgit.git/hooks/post-receive', os.X_OK)
        with open('/tmp/testgit.git/hooks/post-receive') as f: c = f.read()
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

class TestGitCommit(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        self.setup_with_tools()

    @td.with_git
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


class TestGitHtmlView(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        self.setup_with_tools()

    @td.with_git
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
