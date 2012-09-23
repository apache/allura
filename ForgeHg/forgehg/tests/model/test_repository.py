import os
import shutil
import unittest
import pkg_resources
from ConfigParser import ConfigParser

import mock
from ming.base import Object
from ming.orm import ThreadLocalORMSession

from alluratest.controller import setup_basic_test, setup_global_objects
from allura.lib import helpers as h
from allura.tests.model.test_repo import RepoImplTestBase
from allura import model as M

from forgehg import model as HM
from forgehg.tests import with_hg

class TestNewRepo(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        self.setup_with_tools()

    @with_hg
    def setup_with_tools(self):
        setup_global_objects()
        h.set_context('test', 'src-hg', neighborhood='Projects')
        repo_dir = pkg_resources.resource_filename(
            'forgehg', 'tests/data')
        self.repo = HM.Repository(
            name='testrepo.hg',
            fs_path=repo_dir,
            url_path = '/test/',
            tool = 'hg',
            status = 'creating')
        self.repo.refresh()
        self.rev = M.repo.Commit.query.get(_id=self.repo.heads[0]['object_id'])
        self.rev.repo = self.repo
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_redo_trees(self):
        old_tree = self.rev.tree
        del self.rev.tree
        M.repo.Tree.query.remove()
        ThreadLocalORMSession.close_all()
        new_tree =  self.rev.tree
        self.assertEqual(old_tree.tree_ids, new_tree.tree_ids)
        self.assertEqual(old_tree.blob_ids, new_tree.blob_ids)
        self.assertEqual(old_tree._id, new_tree._id)

    def test_commit(self):
        assert self.rev.primary() is self.rev
        assert self.rev.index_id().startswith('allura/model/repo/Commit#')
        self.rev.author_url
        self.rev.committer_url
        assert self.rev.tree._id == self.rev.tree_id
        assert self.rev.summary == self.rev.message.splitlines()[0]
        assert self.rev.shorthand_id() == '[5a0a99]'
        assert self.rev.symbolic_ids == (['default'], ['tip'])
        assert self.rev.url() == (
            '/p/test/src-hg/ci/'
            '5a0a993efa9bce7d1983344261393e841fcfd65d/')
        all_cis = self.repo.log(self.rev._id, 0, 1000)
        assert len(all_cis) == 6
        assert self.repo.log(self.rev._id, 1,1000) == all_cis[1:]
        assert self.repo.log(self.rev._id, 0,3) == all_cis[:3]
        assert self.repo.log(self.rev._id, 1,2) == all_cis[1:3]
        for ci in all_cis:
            ci.context()
        self.rev.tree.ls()
        assert self.rev.tree.readme() == (
            'README', 'This is readme\nAnother line\n')
        assert self.rev.tree.path() == '/'
        assert self.rev.tree.url() == (
            '/p/test/src-hg/ci/'
            '5a0a993efa9bce7d1983344261393e841fcfd65d/'
            'tree/')
        self.rev.tree.by_name['README']
        assert self.rev.tree.is_blob('README') == True

class TestHgRepo(unittest.TestCase, RepoImplTestBase):

    def setUp(self):
        setup_basic_test()
        self.setup_with_tools()

    @with_hg
    def setup_with_tools(self):
        setup_global_objects()
        h.set_context('test', 'src-hg', neighborhood='Projects')
        repo_dir = pkg_resources.resource_filename(
            'forgehg', 'tests/data')
        self.repo = HM.Repository(
            name='testrepo.hg',
            fs_path=repo_dir,
            url_path = '/test/',
            tool = 'hg',
            status = 'creating')
        self.repo.refresh()
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_init(self):
        repo = HM.Repository(
            name='testrepo.hg',
            fs_path='/tmp/',
            url_path = '/test/',
            tool = 'hg',
            status = 'creating')
        dirname = os.path.join(repo.fs_path, repo.name)
        if os.path.exists(dirname):
            shutil.rmtree(dirname)
        repo.init()
        shutil.rmtree(dirname)

    def test_fork(self):
        repo = HM.Repository(
            name='testrepo.hg',
            fs_path='/tmp/',
            url_path = '/test/',
            tool = 'hg',
            status = 'creating')
        repo_path = pkg_resources.resource_filename(
            'forgehg', 'tests/data/testrepo.hg')
        dirname = os.path.join(repo.fs_path, repo.name)
        if os.path.exists(dirname):
            shutil.rmtree(dirname)
        repo.init()
        repo._impl.clone_from(repo_path, copy_hooks=False)
        assert len(repo.log())
        assert not os.path.exists('/tmp/testrepo.hg/.hg/external-changegroup')
        assert not os.path.exists('/tmp/testrepo.hg/.hg/nested/nested-file')
        assert os.path.exists('/tmp/testrepo.hg/.hg/hgrc')
        cp = ConfigParser()
        cp.read('/tmp/testrepo.hg/.hg/hgrc')
        assert not cp.has_section('other')
        assert cp.has_section('hooks')
        assert not cp.has_option('hooks', 'changegroup.external')
        assert not cp.has_option('hooks', 'commit')
        self.assertEquals(cp.get('hooks', 'changegroup.sourceforge'), 'curl -s http://localhost//auth/refresh_repo/p/test/src-hg/')
        assert not os.path.exists('/tmp/testrepo.hg/.hg/undo.branch')
        shutil.rmtree(dirname)

    def test_clone(self):
        repo = HM.Repository(
            name='testrepo.hg',
            fs_path='/tmp/',
            url_path = '/test/',
            tool = 'hg',
            status = 'creating')
        repo_path = pkg_resources.resource_filename(
            'forgehg', 'tests/data/testrepo.hg')
        dirname = os.path.join(repo.fs_path, repo.name)
        if os.path.exists(dirname):
            shutil.rmtree(dirname)
        repo.init()
        repo._impl.clone_from(repo_path, copy_hooks=True)
        assert len(repo.log())
        assert os.path.exists('/tmp/testrepo.hg/.hg/external-changegroup')
        assert os.access('/tmp/testrepo.hg/.hg/external-changegroup', os.X_OK)
        with open('/tmp/testrepo.hg/.hg/external-changegroup') as f: c = f.read()
        self.assertEqual(c,
                '#!/bin/bash\n'
                '\n'
                'echo external-changegroup\n')
        assert os.path.exists('/tmp/testrepo.hg/.hg/nested/nested-file')
        assert os.access('/tmp/testrepo.hg/.hg/nested/nested-file', os.X_OK)
        with open('/tmp/testrepo.hg/.hg/nested/nested-file') as f: c = f.read()
        self.assertEqual(c, 'nested-file\n')
        assert os.path.exists('/tmp/testrepo.hg/.hg/hgrc')
        cp = ConfigParser()
        cp.read('/tmp/testrepo.hg/.hg/hgrc')
        assert cp.has_section('other')
        self.assertEquals(cp.get('other', 'custom'), 'custom value')
        assert cp.has_section('hooks')
        self.assertEquals(cp.get('hooks', 'changegroup.sourceforge'), 'curl -s http://localhost//auth/refresh_repo/p/test/src-hg/')
        self.assertEquals(cp.get('hooks', 'changegroup.external'), '.hg/external-changegroup')
        self.assertEquals(cp.get('hooks', 'commit'), 'python:hgext.notify.hook')
        assert not os.path.exists('/tmp/testrepo.hg/.hg/undo.branch')
        shutil.rmtree(dirname)

    def test_index(self):
        i = self.repo.index()
        assert i['type_s'] == 'Hg Repository', i

    def test_log(self):
        for entry in self.repo.log():
            if entry._id.startswith('00000000'): continue
            assert entry.committed.email == 'rick446@usa.net'
            assert entry.message

    def test_revision(self):
        entry = self.repo.commit('4a7f7ec0dcf5')
        assert entry.committed.email == 'rick446@usa.net'
        assert entry.message
        assert str(entry.committed.date) == "2012-08-29 13:34:26", str(entry.committed.date)
        # Test that sha1s for named refs are looked up in cache first, instead
        # of from disk.
        with mock.patch('forgehg.model.hg.M.repo.Commit.query') as q:
            self.repo.heads.append(Object(name='HEAD', object_id='deadbeef'))
            self.repo.commit('HEAD')
            q.get.assert_called_with(_id='deadbeef')

class TestHgCommit(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        self.setup_with_tools()

    @with_hg
    def setup_with_tools(self):
        setup_global_objects()
        h.set_context('test', 'src-hg', neighborhood='Projects')
        repo_dir = pkg_resources.resource_filename(
            'forgehg', 'tests/data')
        self.repo = HM.Repository(
            name='testrepo.hg',
            fs_path=repo_dir,
            url_path = '/test/',
            tool = 'hg',
            status = 'creating')
        self.repo.refresh()
        self.rev = self.repo.commit('tip')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_redo_trees(self):
        old_tree = self.rev.tree
        del self.rev.tree
        M.repo.Tree.query.remove(dict(type='tree'))
        ThreadLocalORMSession.close_all()
        new_tree =  self.rev.tree
        self.assertEqual(old_tree.tree_ids, new_tree.tree_ids)
        self.assertEqual(old_tree.blob_ids, new_tree.blob_ids)
        self.assertEqual(old_tree._id, new_tree._id)

    def test_url(self):
        assert self.rev.url().endswith('cfd65d/'), \
            self.rev.url()

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
