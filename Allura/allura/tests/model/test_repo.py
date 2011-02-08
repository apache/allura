import os
import unittest
from itertools import count
from datetime import timedelta, datetime

import mock
from pylons import g, c
import tg
import ming
from ming.orm import session, state, ThreadLocalORMSession

from alluratest.controller import setup_basic_test, setup_global_objects
from allura import model as M
from allura.lib import helpers as h


class _Test(unittest.TestCase):
    idgen = ( 'obj_%d' % i for i in count())

    def _make_tree(self, object_id, **kwargs):
        t, isnew = M.Tree.upsert(object_id)
        for k,v in kwargs.iteritems():
            if isinstance(v, basestring):
                obj, isnew = M.Blob.upsert(self.idgen.next())
            else:
                obj = self._make_tree(self.idgen.next(), **v)
            t.object_ids.append(ming.base.Object(
                    name=k, object_id=obj.object_id))
        session(t).flush()
        return t

    def setUp(self):
        setup_basic_test()
        setup_global_objects()
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        self.prefix = tg.config.get('scm.repos.root', '/')

class _TestWithRepo(_Test):
    def setUp(self):
        super(_TestWithRepo, self).setUp()
        h.set_context('test')
        c.project.install_app('svn', 'test1')
        h.set_context('test', 'test1')
        self.repo = M.Repository(name='test1', tool='svn')
        self.repo._impl = mock.Mock(spec=M.RepositoryImplementation())
        self.repo._impl.log = lambda *a,**kw:(['foo'], [])
        self.repo._impl._repo = self.repo
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def _make_commit(self, object_id, **tree_parts):
        ci, isnew = M.Commit.upsert(object_id)
        if isnew:
            ci.committed.email=c.user.email_addresses[0]
            ci.authored.email=c.user.email_addresses[0]
            ci.authored.date = datetime.utcnow()
            ci.message='summary\n\nddescription'
            ci.set_context(self.repo)
            ci.tree_id = 't_' + object_id
            ci.tree = self._make_tree(ci.tree_id, **tree_parts)
        return ci, isnew
        
class _TestWithRepoAndCommit(_TestWithRepo):
    def setUp(self):
        super(_TestWithRepoAndCommit, self).setUp()
        self.ci, isnew = self._make_commit('foo')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

class TestRepo(_TestWithRepo):

    def test_create(self):
        assert self.repo.fs_path == os.path.join(self.prefix, 'svn/p/test/')
        assert self.repo.url_path == '/p/test/'
        assert self.repo.full_fs_path == os.path.join(self.prefix, 'svn/p/test/test1')

    def test_passthrough(self):
        argless = ['init']
        for fn in argless:
            getattr(self.repo, fn)()
            getattr(self.repo._impl, fn).assert_called_with()
        unary = [ 'commit', 'commit_context', 'open_blob', 'shorthand_for_commit', 'url_for_commit' ]
        for fn in unary:
            getattr(self.repo, fn)('foo')
            getattr(self.repo._impl, fn).assert_called_with('foo')

    def test_init_as_clone(self):
        self.repo.init_as_clone('srcpath', 'srcname', 'srcurl')
        assert self.repo.upstream_repo.name == 'srcname'
        assert self.repo.upstream_repo.url == 'srcurl'
        assert self.repo._impl.clone_from.called_with('srcpath')

    def test_log(self):
        ci = mock.Mock()
        ci.log = mock.Mock(return_value=[1,2,3])
        self.repo._impl.commit = mock.Mock(return_value=ci)
        assert self.repo.log() == [1,2,3], self.repo.log()

    def test_count_revisions(self):
        ci = mock.Mock()
        ci.count_revisions = mock.Mock(return_value=42)
        self.repo._impl.commit = mock.Mock(return_value=ci)
        assert self.repo.count() == 42

    def test_latest(self):
        ci = mock.Mock()
        self.repo._impl.commit = mock.Mock(return_value=ci)
        assert self.repo.latest() is ci

    def test_index(self):
        i = self.repo.index()
        assert i['type_s'] == 'Repository', i
        assert i['name_s'] == 'test1', i

    def test_scm_host_url(self):
        assert (
            self.repo.readwrite_path('nobody')
            == 'svn+ssh://nobody@localhost:8022/scm-repo/p/test/test1'),\
            self.repo.readwrite_path('nobody')

    def test_merge_request(self):
        M.MergeRequest.upsert(app_config_id=c.app.config._id, status='open')
        M.MergeRequest.upsert(app_config_id=c.app.config._id, status='closed')
        session(M.MergeRequest).flush()
        session(M.MergeRequest).clear()
        assert self.repo.merge_requests_by_statuses('open').count() == 1
        assert self.repo.merge_requests_by_statuses('closed').count() == 1
        assert self.repo.merge_requests_by_statuses('open', 'closed').count() == 2

    def test_guess_type(self):
        assert self.repo.guess_type('foo.txt') == ('text/plain', None)
        assert self.repo.guess_type('foo.gbaer') == ('application/octet-stream', None)
        assert self.repo.guess_type('foo.html') == ('text/html', None)
        assert self.repo.guess_type('.gitignore') == ('text/plain', None)

    def test_refresh(self):
        ci = mock.Mock()
        ci.count_revisions=mock.Mock(return_value=100)
        ci.diffs_computed = False
        self.repo._impl.commit = mock.Mock(return_value=ci)
        self.repo._impl.new_commits = mock.Mock(return_value=['foo%d' % i for i in range(100) ])
        def set_heads():
            self.repo.heads = [ ming.base.Object(name='head', object_id='foo0', count=100) ]
        self.repo._impl.refresh_heads = mock.Mock(side_effect=set_heads)
        self.repo.refresh()
        ci.compute_diffs.assert_called_with()

    def test_push_upstream_context(self):
        self.repo.init_as_clone('srcpath', 'srcname', '/p/test/svn/')
        old_app_instance = M.Project.app_instance
        try:
            M.Project.app_instance = mock.Mock()
            with self.repo.push_upstream_context():
                assert c.project.shortname == 'test'
        finally:
            M.Project.app_instance = old_app_instance

    def test_pending_upstream_merges(self):
        self.repo.init_as_clone('srcpath', 'srcname', '/p/test/svn/')
        old_app_instance = M.Project.app_instance
        try:
            M.Project.app_instance = mock.Mock()
            self.repo.pending_upstream_merges()
        finally:
            M.Project.app_instance = old_app_instance

class TestMergeRequest(_TestWithRepoAndCommit):

    def setUp(self):
        super(TestMergeRequest, self).setUp()
        c.project.install_app('svn', 'test2')
        h.set_context('test', 'test2')
        self.repo2 = M.Repository(name='test2', tool='svn')
        self.repo2._impl = mock.Mock(spec=M.RepositoryImplementation())
        self.repo2._impl.log = lambda *a,**kw:(['foo'], [])
        self.repo2._impl._repo = self.repo2
        self.repo2.init_as_clone('/p/test/', 'test1', '/p/test/test1/')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_upsert(self):
        h.set_context('test', 'test1')
        mr = M.MergeRequest.upsert(
            downstream=ming.base.Object(
                project_id=c.project._id,
                mount_point='test2',
                commit_id='foo'),
            target_branch='foobranch',
            summary='summary',
            description='description')
        u = M.User.by_username('test-admin')
        assert mr.creator == u
        assert mr.creator_name == u.display_name
        assert mr.creator_url == u.url()
        assert mr.downstream_url == '/p/test/test2/'
        assert mr.downstream_repo_url == 'http://svn.localhost/p/test/test2'
        assert mr.commits == [ self._make_commit('foo')[0] ]

class TestLastCommitFor(_TestWithRepoAndCommit):

    def test_upsert(self):
        h.set_context('test', 'test1')
        lcf, isnew = M.LastCommitFor.upsert(repo_id=c.app.repo._id, object_id=self.ci.object_id)

class TestRepoObject(_TestWithRepoAndCommit):

    def test_upsert(self):
        obj0, isnew0 = M.RepoObject.upsert('foo1')
        obj1, isnew1 = M.RepoObject.upsert('foo1')
        assert obj0 is obj1
        assert isnew0 and not isnew1

    def test_set_last_commit(self):
        obj, isnew = M.RepoObject.upsert('foo1')
        lc, isnew = obj.set_last_commit(self.ci)

    def test_get_last_commit(self):
        obj, isnew = M.RepoObject.upsert('foo1')
        lc, isnew = obj.set_last_commit(self.ci)
        assert lc.last_commit is obj.get_last_commit()

    def test_get_last_commit_missing(self):
        obj, isnew = M.RepoObject.upsert('foo1')
        assert obj.get_last_commit()['id'] is None

    def test_artifact_methods(self):
        assert self.ci.index_id() == '<Commit foo>', self.ci.index_id()
        assert self.ci.primary() is self.ci, self.ci.primary()

class TestLogCache(_TestWithRepo):

    def test_get(self):
        lc = M.LogCache.get(self.repo, 'foo')
        assert lc.object_id == '$foo', lc.object_id

class TestCommit(_TestWithRepo):

    def setUp(self):
        super(TestCommit, self).setUp()
        self.ci, isnew = self._make_commit(
            'foo', 
            a=dict(
                a=dict(
                    a='',
                    b='',),
                b=''))
        self.tree = self.ci.tree
        impl = M.RepositoryImplementation()
        impl._repo = self.repo
        self.repo._impl.shorthand_for_commit = impl.shorthand_for_commit
        self.repo._impl.url_for_commit = impl.url_for_commit

    def test_upsert(self):
        obj0, isnew0 = M.Commit.upsert('foo')
        obj1, isnew1 = M.Commit.upsert('foo')
        assert obj0 is obj1
        assert not isnew1
        assert not self.ci.diffs_computed
        u = M.User.by_username('test-admin')
        assert self.ci.author_url == u.url()
        assert self.ci.committer_url == u.url()
        assert self.ci.tree is self.tree
        assert self.ci.summary == 'summary'
        assert self.ci.shorthand_id() == '[foo]'
        assert self.ci.url() == '/p/test/test1/ci/foo/'

    def test_get_path(self):
        b = self.ci.get_path('a/a/a')
        assert isinstance(b, M.Blob)
        assert self.ci.get_path('a/a') is None
        
    def test_log(self):
        commits = self.ci.log(0, 100)
        assert commits[0].object_id == 'foo'

    def test_count_revisions(self):
        assert self.ci.count_revisions() == 1

    def test_compute_diffs(self):
        self.repo._impl.commit = mock.Mock(return_value=self.ci)
        self.ci.compute_diffs()
        assert self.ci.diffs_computed == True
        assert self.ci.diffs.added == [ '/a' ]
        assert (self.ci.diffs.copied
                == self.ci.diffs.changed
                == self.ci.diffs.removed
                == [])
        ci, isnew = self._make_commit('bar')
        ci.parent_ids = [ 'foo' ]
        ci.compute_diffs()
        assert ci.diffs_computed == True
        assert ci.diffs.removed == [ '/a/' ]
        assert (ci.diffs.copied
                == ci.diffs.changed
                == ci.diffs.added
                == [])
        ci, isnew = self._make_commit(
            'baz', 
            b=dict(
                a=dict(
                    a='',
                    b='',),
                b=''))
        ci.parent_ids = [ 'foo' ]
        ci.compute_diffs()
        assert ci.diffs_computed == True
        assert ci.diffs.added == [ '/b/' ]
        assert ci.diffs.removed == [ '/a/' ]
        assert (ci.diffs.copied
                == ci.diffs.changed
                == [])
    
    def test_context(self):
        self.ci.context()

