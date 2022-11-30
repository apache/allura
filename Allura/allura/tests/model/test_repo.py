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

from datetime import datetime
from collections import defaultdict, OrderedDict

import unittest
import mock
from tg import tmpl_context as c
from bson import ObjectId
from ming.orm import session
from tg import config

from alluratest.controller import setup_basic_test, setup_global_objects
from allura import model as M
from allura.lib import helpers as h


class TestGitLikeTree:
    def test_set_blob(self):
        tree = M.GitLikeTree()
        tree.set_blob('/dir/dir2/file', 'file-oid')

        assert tree.blobs == {}
        assert tree.get_tree('dir').blobs == {}
        assert (tree.get_tree('dir').get_tree('dir2')
                     .blobs == {'file': 'file-oid'})

    def test_hex(self):
        tree = M.GitLikeTree()
        tree.set_blob('/dir/dir2/file', 'file-oid')
        hex = tree.hex()

        # check the reprs. In case hex (below) fails, this'll be useful
        assert (repr(tree.get_tree('dir').get_tree('dir2')) ==
                     'b file-oid file')
        assert (repr(tree) ==
                     't 96af1772ecce1e6044e6925e595d9373ffcd2615 dir')
        # the hex() value shouldn't change, it's an important key
        assert hex == '4abba29a43411b9b7cecc1a74f0b27920554350d'

        # another one should be the same
        tree2 = M.GitLikeTree()
        tree2.set_blob('/dir/dir2/file', 'file-oid')
        hex2 = tree2.hex()
        assert hex == hex2

    def test_hex_with_unicode(self):
        tree = M.GitLikeTree()
        tree.set_blob('/dir/f•º£', 'file-oid')
        # the hex() value shouldn't change, it's an important key
        assert tree.hex() == '51ce65bead2f6452da61d4f6f2e42f8648bf9e4b'


class RepoImplTestBase:
    pass


class RepoTestBase(unittest.TestCase):
    def setup_method(self, method):
        setup_basic_test()

    @mock.patch('allura.model.repository.Repository.url')
    def test_refresh_url(self, url):
        url.return_value = '/p/test/repo'
        c.app = mock.Mock(**{'config._id': 'deadbeef'})
        repo = M.repository.Repository()
        cases = [
            [
                None,
                'http://localhost:8080/auth/refresh_repo/p/test/repo',
            ],
            [
                'https://somewhere.com',
                'https://somewhere.com/auth/refresh_repo/p/test/repo',
            ],
            [
                'http://somewhere.com/',
                'http://somewhere.com/auth/refresh_repo/p/test/repo',
            ]]
        for base_url, result in cases:
            values = {}
            if base_url:
                values['base_url'] = base_url
            with mock.patch.dict(config, values, clear=True):
                self.assertEqual(result, repo.refresh_url())

    def test_clone_command_categories(self):
        c.app = mock.Mock(**{'config._id': 'deadbeef'})
        repo = M.repository.Repository(tool='git')
        cmd_cats = repo.clone_command_categories(anon=False)
        assert cmd_cats == [
            {'key': 'file', 'name': 'File', 'title': 'Filesystem'}
        ]

        cmd_cats = repo.clone_command_categories(anon=True)
        assert cmd_cats == [
            {'key': 'file', 'name': 'File', 'title': 'Filesystem'}
        ]

        repo = M.repository.Repository(tool='something-else')  # no "something-else" in config so will use defaults
        cmd_cats = repo.clone_command_categories(anon=False)
        assert cmd_cats == [
            {'key': 'rw', 'name': 'RW', 'title': 'Read/Write'},
            {'key': 'ro', 'name': 'RO', 'title': 'Read Only'},
            {'key': 'https', 'name': 'HTTPS', 'title': 'HTTPS'}
        ]

        cmd_cats = repo.clone_command_categories(anon=True)
        assert cmd_cats == [
            {'key': 'ro', 'name': 'RO', 'title': 'Read Only'},
            {'key': 'https_anon', 'name': 'HTTPS', 'title': 'HTTPS'}
        ]


class TestLastCommit(unittest.TestCase):
    def setup_method(self, method):
        setup_basic_test()
        setup_global_objects()
        self.repo = mock.Mock(
            name='repo',
            _commits=OrderedDict(),
            _last_commit=None,
        )
        self.repo.paged_diffs.return_value = {
            'added': [],
            'removed': [],
            'copied': [],
            'renamed': [],
            'changed': [],
            'total': 0,
        }
        self.repo.shorthand_for_commit = lambda _id: _id[:6]
        self.repo.rev_to_commit_id = lambda rev: rev
        self.repo.log = self._log
        self._changes = defaultdict(list)
        self.repo.get_changes = lambda _id: self._changes[_id]
        self._last_commits = [(None, set())]
        self.repo._get_last_commit = lambda i, p: self._last_commits.pop()
        lcids = M.repository.RepositoryImplementation.last_commit_ids
        lcids = getattr(lcids, '__func__', lcids)
        self.repo.last_commit_ids = lambda *a, **k: lcids(self.repo, *a, **k)
        c.lcid_cache = {}

    def _build_tree(self, commit, path, tree_paths):
        tree_nodes = []
        blob_nodes = []
        sub_paths = defaultdict(list)

        def n(p):
            m = mock.Mock()
            m.name = p
            return m

        for p in tree_paths:
            if '/' in p:
                node, sub = p.split('/', 1)
                if node not in sub_paths:
                    tree_nodes.append(n(node))
                sub_paths[node].append(sub)
            else:
                blob_nodes.append(n(p))
        tree = mock.Mock(
            commit=commit,
            path=mock.Mock(return_value=path),
            tree_ids=tree_nodes,
            blob_ids=blob_nodes,
            other_ids=[],
            repo=self.repo,
        )
        tree.get_obj_by_path = lambda p: self._build_tree(
            commit, p, sub_paths[p])
        tree.__getitem__ = lambda s, p: self._build_tree(
            commit, p, sub_paths[p])
        return tree

    def _add_commit(self, msg, tree_paths, diff_paths=None, parents=[]):
        suser = dict(
            name='test',
            email='test@example.com',
            date=datetime(2013, 1, 1 + len(self.repo._commits)),
        )
        commit = M.repository.Commit(
            _id=str(ObjectId()),
            message=msg,
            parent_ids=[parent._id for parent in parents],
            commited=suser,
            authored=suser,
            repo=self.repo,
        )
        commit.tree = self._build_tree(commit, '/', tree_paths)
        commit.get_tree = lambda c: commit.tree
        self._changes[commit._id].extend(diff_paths or tree_paths)
        self.repo._commits[commit._id] = commit
        self._last_commits.append((commit._id, set(diff_paths or tree_paths)))
        return commit

    def _log(self, revs, path, id_only=True, limit=None):
        for commit_id, commit in reversed(list(self.repo._commits.items())):
            if path in commit.changed_paths:
                yield commit_id

    def test_single_commit(self):
        commit1 = self._add_commit('Commit 1', [
            'file1',
            'dir1/file2',
        ])
        lcd = M.repository.LastCommit.get(commit1.tree)
        self.assertEqual(self.repo._commits[lcd.commit_id].message, commit1.message)
        self.assertEqual(lcd.path, '')
        self.assertEqual(len(lcd.entries), 2)
        self.assertEqual(lcd.by_name['file1'], commit1._id)
        self.assertEqual(lcd.by_name['dir1'], commit1._id)

    def test_multiple_commits_no_overlap(self):
        commit1 = self._add_commit('Commit 1', ['file1'])
        commit2 = self._add_commit('Commit 2', ['file1', 'dir1/file1'], ['dir1/file1'], [commit1])
        commit3 = self._add_commit('Commit 3', ['file1', 'dir1/file1', 'file2'], ['file2'], [commit2])
        lcd = M.repository.LastCommit.get(commit3.tree)
        self.assertEqual(self.repo._commits[lcd.commit_id].message, commit3.message)
        self.assertEqual(lcd.commit_id, commit3._id)
        self.assertEqual(lcd.path, '')
        self.assertEqual(len(lcd.entries), 3)
        self.assertEqual(lcd.by_name['file1'], commit1._id)
        self.assertEqual(lcd.by_name['dir1'], commit2._id)
        self.assertEqual(lcd.by_name['file2'], commit3._id)

    def test_multiple_commits_with_overlap(self):
        commit1 = self._add_commit('Commit 1', ['file1'])
        commit2 = self._add_commit('Commit 2', ['file1', 'dir1/file1'], ['dir1/file1'], [commit1])
        commit3 = self._add_commit('Commit 3', ['file1', 'dir1/file1', 'file2'], ['file1', 'file2'], [commit2])
        lcd = M.repository.LastCommit.get(commit3.tree)
        self.assertEqual(self.repo._commits[lcd.commit_id].message, commit3.message)
        self.assertEqual(lcd.path, '')
        self.assertEqual(len(lcd.entries), 3)
        self.assertEqual(lcd.by_name['file1'], commit3._id)
        self.assertEqual(lcd.by_name['dir1'], commit2._id)
        self.assertEqual(lcd.by_name['file2'], commit3._id)

    def test_multiple_commits_subdir_change(self):
        commit1 = self._add_commit('Commit 1', ['file1', 'dir1/file1'])
        commit2 = self._add_commit('Commit 2', ['file1', 'dir1/file1', 'dir1/file2'], ['dir1/file2'], [commit1])
        commit3 = self._add_commit('Commit 3', ['file1', 'dir1/file1', 'dir1/file2'], ['dir1/file1'], [commit2])
        lcd = M.repository.LastCommit.get(commit3.tree)
        self.assertEqual(self.repo._commits[lcd.commit_id].message, commit3.message)
        self.assertEqual(lcd.path, '')
        self.assertEqual(len(lcd.entries), 2)
        self.assertEqual(lcd.by_name['file1'], commit1._id)
        self.assertEqual(lcd.by_name['dir1'], commit3._id)

    def test_subdir_lcd(self):
        commit1 = self._add_commit('Commit 1', ['file1', 'dir1/file1'])
        commit2 = self._add_commit('Commit 2', ['file1', 'dir1/file1', 'dir1/file2'], ['dir1/file2'], [commit1])
        commit3 = self._add_commit('Commit 3', ['file1', 'dir1/file1', 'dir1/file2'], ['dir1/file1'], [commit2])
        tree = self._build_tree(commit3, '/dir1', ['file1', 'file2'])
        lcd = M.repository.LastCommit.get(tree)
        self.assertEqual(self.repo._commits[lcd.commit_id].message, commit3.message)
        self.assertEqual(lcd.path, 'dir1')
        self.assertEqual(len(lcd.entries), 2)
        self.assertEqual(lcd.by_name['file1'], commit3._id)
        self.assertEqual(lcd.by_name['file2'], commit2._id)

    def test_subdir_lcd_prev_commit(self):
        commit1 = self._add_commit('Commit 1', ['file1', 'dir1/file1'])
        commit2 = self._add_commit('Commit 2', ['file1', 'dir1/file1', 'dir1/file2'], ['dir1/file2'], [commit1])
        commit3 = self._add_commit('Commit 3', ['file1', 'dir1/file1', 'dir1/file2'], ['dir1/file1'], [commit2])
        commit4 = self._add_commit('Commit 4', ['file1', 'dir1/file1', 'dir1/file2', 'file2'], ['file2'], [commit3])
        tree = self._build_tree(commit4, '/dir1', ['file1', 'file2'])
        lcd = M.repository.LastCommit.get(tree)
        self.assertEqual(self.repo._commits[lcd.commit_id].message, commit3.message)
        self.assertEqual(lcd.path, 'dir1')
        self.assertEqual(len(lcd.entries), 2)
        self.assertEqual(lcd.by_name['file1'], commit3._id)
        self.assertEqual(lcd.by_name['file2'], commit2._id)

    def test_subdir_lcd_always_empty(self):
        commit1 = self._add_commit('Commit 1', ['file1', 'dir1'])
        commit2 = self._add_commit('Commit 2', ['file1', 'file2'], ['file2'], [commit1])
        tree = self._build_tree(commit2, '/dir1', [])
        lcd = M.repository.LastCommit.get(tree)
        self.assertEqual(self.repo._commits[lcd.commit_id].message, commit1.message)
        self.assertEqual(lcd.path, 'dir1')
        self.assertEqual(lcd.entries, [])

    def test_subdir_lcd_emptied(self):
        commit1 = self._add_commit('Commit 1', ['file1', 'dir1/file1'])
        commit2 = self._add_commit('Commit 2', ['file1'], ['dir1/file1'], [commit1])
        tree = self._build_tree(commit2, '/dir1', [])
        lcd = M.repository.LastCommit.get(tree)
        self.assertEqual(self.repo._commits[lcd.commit_id].message, commit2.message)
        self.assertEqual(lcd.path, 'dir1')
        self.assertEqual(lcd.entries, [])

    def test_existing_lcd_unchained(self):
        commit1 = self._add_commit('Commit 1', ['file1', 'dir1/file1'])
        commit2 = self._add_commit('Commit 2', ['file1', 'dir1/file1', 'dir1/file2'], ['dir1/file2'], [commit1])
        commit3 = self._add_commit('Commit 3', ['file1', 'dir1/file1', 'dir1/file2'], ['file1'], [commit2])
        prev_lcd = M.repository.LastCommit(
            path='dir1',
            commit_id=commit2._id,
            entries=[
                dict(
                    name='file1',
                    commit_id=commit1._id),
                dict(
                    name='file2',
                    commit_id=commit2._id),
            ],
        )
        session(prev_lcd).flush()
        tree = self._build_tree(commit3, '/dir1', ['file1', 'file2'])
        lcd = M.repository.LastCommit.get(tree)
        self.assertEqual(lcd._id, prev_lcd._id)
        self.assertEqual(self.repo._commits[lcd.commit_id].message, commit2.message)
        self.assertEqual(lcd.path, 'dir1')
        self.assertEqual(lcd.entries, prev_lcd.entries)

    def test_existing_lcd_partial(self):
        commit1 = self._add_commit('Commit 1', ['file1'])
        commit2 = self._add_commit('Commit 2', ['file1', 'file2'], ['file2'], [commit1])
        commit3 = self._add_commit('Commit 3', ['file1', 'file2', 'file3'], ['file3'], [commit2])
        commit4 = self._add_commit('Commit 4', ['file1', 'file2', 'file3', 'file4'], ['file2', 'file4'], [commit3])
        prev_lcd = M.repository.LastCommit(
            path='',
            commit_id=commit3._id,
            entries=[
                dict(
                    name='file1',
                    commit_id=commit1._id),
                dict(
                    name='file2',
                    commit_id=commit2._id),
                dict(
                    name='file3',
                    commit_id=commit3._id),
            ],
        )
        session(prev_lcd).flush()
        lcd = M.repository.LastCommit.get(commit4.tree)
        self.assertEqual(self.repo._commits[lcd.commit_id].message, commit4.message)
        self.assertEqual(lcd.path, '')
        self.assertEqual(len(lcd.entries), 4)
        self.assertEqual(lcd.by_name['file1'], commit1._id)
        self.assertEqual(lcd.by_name['file2'], commit4._id)
        self.assertEqual(lcd.by_name['file3'], commit3._id)
        self.assertEqual(lcd.by_name['file4'], commit4._id)

    def test_missing_add_record(self):
        self._add_commit('Commit 1', ['file1'])
        commit2 = self._add_commit('Commit 2', ['file2'])
        commit2.changed_paths = []
        result = self.repo.last_commit_ids(commit2, ['file2'])
        assert result == {'file2': commit2._id}

    def test_missing_add_record_first_commit(self):
        commit1 = self._add_commit('Commit 1', ['file1'])
        commit1.changed_paths = []
        result = self.repo.last_commit_ids(commit1, ['file1'])
        assert result == {'file1': commit1._id}

    def test_timeout(self):
        commit1 = self._add_commit('Commit 1', ['file1'])
        commit2 = self._add_commit('Commit 2', ['file1', 'dir1/file1'], ['dir1/file1'], [commit1])
        commit3 = self._add_commit('Commit 3', ['file1', 'dir1/file1', 'file2'], ['file2'], [commit2])
        with h.push_config(config, lcd_timeout=-1000):
            lcd = M.repository.LastCommit.get(commit3.tree)
        self.assertEqual(self.repo._commits[lcd.commit_id].message, commit3.message)
        self.assertEqual(lcd.commit_id, commit3._id)
        self.assertEqual(lcd.path, '')
        self.assertEqual(len(lcd.entries), 1)
        self.assertEqual(lcd.by_name['file2'], commit3._id)

    def test_loop(self):
        commit1 = self._add_commit('Commit 1', ['file1'])
        commit2 = self._add_commit('Commit 2', ['file1', 'dir1/file1'], ['dir1/file1'], [commit1])
        commit3 = self._add_commit('Commit 3', ['file1', 'dir1/file1', 'file2'], ['file2'], [commit2])
        commit2.parent_ids = [commit3._id]
        session(commit2).flush(commit2)
        lcd = M.repository.LastCommit.get(commit3.tree)
        self.assertEqual(self.repo._commits[lcd.commit_id].message, commit3.message)
        self.assertEqual(lcd.commit_id, commit3._id)
        self.assertEqual(lcd.path, '')
        self.assertEqual(len(lcd.entries), 3)
        self.assertEqual(lcd.by_name['dir1'], commit2._id)
        self.assertEqual(lcd.by_name['file2'], commit3._id)


class TestModelCache(unittest.TestCase):
    def setup_method(self, method):
        self.cache = M.repository.ModelCache()

    def test_normalize_query(self):
        self.assertEqual(self.cache._normalize_query(
            {'foo': 1, 'bar': 2}), (('bar', 2), ('foo', 1)))

    def test_model_query(self):
        q = mock.Mock(spec_set=['query'], query='foo')
        m = mock.Mock(spec_set=['m'], m='bar')
        n = mock.Mock(spec_set=['foo'], foo='qux')
        self.assertEqual(self.cache._model_query(q), 'foo')
        self.assertEqual(self.cache._model_query(m), 'bar')
        self.assertRaises(AttributeError, self.cache._model_query, [n])

    @mock.patch.object(M.repository.Tree.query, 'get')
    @mock.patch.object(M.repository.LastCommit.query, 'get')
    def test_get(self, lc_get, tr_get):
        tree = tr_get.return_value = mock.Mock(
            spec=['_id', 'val'], _id='foo', val='bar')
        lcd = lc_get.return_value = mock.Mock(
            spec=['_id', 'val'], _id='foo', val='qux')

        val = self.cache.get(M.repository.Tree, {'_id': 'foo'})
        tr_get.assert_called_with(_id='foo')
        self.assertEqual(val, tree)

        val = self.cache.get(M.repository.LastCommit, {'_id': 'foo'})
        lc_get.assert_called_with(_id='foo')
        self.assertEqual(val, lcd)

    @mock.patch.object(M.repository.Tree.query, 'get')
    def test_get_no_query(self, tr_get):
        tree1 = tr_get.return_value = mock.Mock(
            spec=['_id', 'val'], _id='foo', val='bar')
        val = self.cache.get(M.repository.Tree, {'_id': 'foo'})
        tr_get.assert_called_once_with(_id='foo')
        self.assertEqual(val, tree1)

        tree2 = tr_get.return_value = mock.Mock(_id='foo', val='qux')
        val = self.cache.get(M.repository.Tree, {'_id': 'foo'})
        tr_get.assert_called_once_with(_id='foo')
        self.assertEqual(val, tree1)

    def test_set(self):
        tree = mock.Mock(spec=['_id', 'test_set'], _id='foo', val='test_set')
        self.cache.set(M.repository.Tree, {'val': 'test_set'}, tree)
        self.assertEqual(self.cache._query_cache,
                         {M.repository.Tree: {(('val', 'test_set'),): 'foo'}})
        self.assertEqual(self.cache._instance_cache,
                         {M.repository.Tree: {'foo': tree}})

    @mock.patch('bson.ObjectId')
    def test_set_none_id(self, obj_id):
        obj_id.return_value = 'OBJID'
        tree = mock.Mock(spec=['_id', 'test_set'], _id=None, val='test_set')
        self.cache.set(M.repository.Tree, {'val1': 'test_set1'}, tree)
        self.cache.set(M.repository.Tree, {'val2': 'test_set2'}, tree)
        self.assertEqual(dict(self.cache._query_cache[M.repository.Tree]), {
            (('val1', 'test_set1'),): 'OBJID',
            (('val2', 'test_set2'),): 'OBJID',
        })
        self.assertEqual(self.cache._instance_cache,
                         {M.repository.Tree: {'OBJID': tree}})
        tree._id = '_id'
        self.assertEqual(self.cache.get(M.repository.Tree, {'val1': 'test_set1'}), tree)
        self.assertEqual(self.cache.get(M.repository.Tree, {'val2': 'test_set2'}), tree)
        self.cache.set(M.repository.Tree, {'val1': 'test_set2'}, tree)
        self.assertEqual(self.cache.get(M.repository.Tree, {'val1': 'test_set1'}), tree)
        self.assertEqual(self.cache.get(M.repository.Tree, {'val2': 'test_set2'}), tree)

    @mock.patch('bson.ObjectId')
    def test_set_none_val(self, obj_id):
        obj_id.return_value = 'OBJID'
        self.cache.set(M.repository.Tree, {'val1': 'test_set1'}, None)
        self.cache.set(M.repository.Tree, {'val2': 'test_set2'}, None)
        self.assertEqual(dict(self.cache._query_cache[M.repository.Tree]), {
            (('val1', 'test_set1'),): None,
            (('val2', 'test_set2'),): None,
        })
        self.assertEqual(dict(self.cache._instance_cache[M.repository.Tree]), {})
        tree1 = mock.Mock(spec=['_id', 'val'], _id='tree1', val='test_set')
        tree2 = mock.Mock(spec=['_model_cache_id', '_id', 'val'],
                          _model_cache_id='tree2', _id='tree1', val='test_set2')
        self.cache.set(M.repository.Tree, {'val1': 'test_set1'}, tree1)
        self.cache.set(M.repository.Tree, {'val2': 'test_set2'}, tree2)
        self.assertEqual(dict(self.cache._query_cache[M.repository.Tree]), {
            (('val1', 'test_set1'),): 'tree1',
            (('val2', 'test_set2'),): 'tree2',
        })
        self.assertEqual(dict(self.cache._instance_cache[M.repository.Tree]), {
            'tree1': tree1,
            'tree2': tree2,
        })

    def test_instance_ids(self):
        tree1 = mock.Mock(spec=['_id', 'val'], _id='id1', val='tree1')
        tree2 = mock.Mock(spec=['_id', 'val'], _id='id2', val='tree2')
        self.cache.set(M.repository.Tree, {'val': 'tree1'}, tree1)
        self.cache.set(M.repository.Tree, {'val': 'tree2'}, tree2)
        self.assertEqual(set(self.cache.instance_ids(M.repository.Tree)),
                         {'id1', 'id2'})
        self.assertEqual(self.cache.instance_ids(M.repository.LastCommit), [])

    @mock.patch.object(M.repository.Tree.query, 'find')
    def test_batch_load(self, tr_find):
        # cls, query, attrs
        m1 = mock.Mock(spec=['_id', 'foo', 'qux'], _id='id1', foo=1, qux=3)
        m2 = mock.Mock(spec=['_id', 'foo', 'qux'], _id='id2', foo=2, qux=5)
        tr_find.return_value = [m1, m2]

        self.cache.batch_load(M.repository.Tree, {'foo': {'$in': 'bar'}})
        tr_find.assert_called_with({'foo': {'$in': 'bar'}})
        self.assertEqual(self.cache._query_cache[M.repository.Tree], {
            (('foo', 1),): 'id1',
            (('foo', 2),): 'id2',
        })
        self.assertEqual(self.cache._instance_cache[M.repository.Tree], {
            'id1': m1,
            'id2': m2,
        })

    @mock.patch.object(M.repository.Tree.query, 'find')
    def test_batch_load_attrs(self, tr_find):
        # cls, query, attrs
        m1 = mock.Mock(spec=['_id', 'foo', 'qux'], _id='id1', foo=1, qux=3)
        m2 = mock.Mock(spec=['_id', 'foo', 'qux'], _id='id2', foo=2, qux=5)
        tr_find.return_value = [m1, m2]

        self.cache.batch_load(M.repository.Tree, {'foo': {'$in': 'bar'}}, ['qux'])
        tr_find.assert_called_with({'foo': {'$in': 'bar'}})
        self.assertEqual(self.cache._query_cache[M.repository.Tree], {
            (('qux', 3),): 'id1',
            (('qux', 5),): 'id2',
        })
        self.assertEqual(self.cache._instance_cache[M.repository.Tree], {
            'id1': m1,
            'id2': m2,
        })

    def test_pruning(self):
        cache = M.repository.ModelCache(max_queries=3, max_instances=2)
        # ensure cache expires as LRU
        tree1 = mock.Mock(spec=['_id', '_val'], _id='foo', val='bar')
        tree2 = mock.Mock(spec=['_id', '_val'], _id='qux', val='fuz')
        tree3 = mock.Mock(spec=['_id', '_val'], _id='f00', val='b4r')
        tree4 = mock.Mock(spec=['_id', '_val'], _id='foo', val='zaz')
        cache.set(M.repository.Tree, {'_id': 'foo'}, tree1)
        cache.set(M.repository.Tree, {'_id': 'qux'}, tree2)
        cache.set(M.repository.Tree, {'_id': 'f00'}, tree3)
        cache.set(M.repository.Tree, {'_id': 'foo'}, tree4)
        cache.get(M.repository.Tree, {'_id': 'f00'})
        cache.set(M.repository.Tree, {'val': 'b4r'}, tree3)
        self.assertEqual(cache._query_cache, {
            M.repository.Tree: {
                (('_id', 'foo'),): 'foo',
                (('_id', 'f00'),): 'f00',
                (('val', 'b4r'),): 'f00',
            },
        })
        self.assertEqual(cache._instance_cache, {
            M.repository.Tree: {
                'f00': tree3,
                'foo': tree4,
            },
        })

    def test_pruning_query_vs_instance(self):
        cache = M.repository.ModelCache(max_queries=3, max_instances=2)
        # ensure cache expires as LRU
        tree1 = mock.Mock(spec=['_id', '_val'], _id='keep', val='bar')
        tree2 = mock.Mock(spec=['_id', '_val'], _id='tree2', val='fuz')
        tree3 = mock.Mock(spec=['_id', '_val'], _id='tree3', val='b4r')
        tree4 = mock.Mock(spec=['_id', '_val'], _id='tree4', val='zaz')
        cache.set(M.repository.Tree, {'keep_query_1': 'bar'}, tree1)
        cache.set(M.repository.Tree, {'drop_query_1': 'bar'}, tree2)
        # should refresh tree1 in _instance_cache
        cache.set(M.repository.Tree, {'keep_query_2': 'bar'}, tree1)
        # should drop tree2, not tree1, from _instance_cache
        cache.set(M.repository.Tree, {'drop_query_2': 'bar'}, tree3)
        self.assertEqual(cache._query_cache[M.repository.Tree], {
            (('drop_query_1', 'bar'),): 'tree2',
            (('keep_query_2', 'bar'),): 'keep',
            (('drop_query_2', 'bar'),): 'tree3',
        })
        self.assertEqual(cache._instance_cache[M.repository.Tree], {
            'keep': tree1,
            'tree3': tree3,
        })

    @mock.patch('bson.ObjectId')
    def test_pruning_no_id(self, obj_id):
        obj_id.side_effect = ['id1', 'id2', 'id3']
        cache = M.repository.ModelCache(max_queries=3, max_instances=2)
        # ensure cache considers same instance equal to itself, even if no _id
        tree1 = mock.Mock(spec=['val'], val='bar')
        cache.set(M.repository.Tree, {'query_1': 'bar'}, tree1)
        cache.set(M.repository.Tree, {'query_2': 'bar'}, tree1)
        cache.set(M.repository.Tree, {'query_3': 'bar'}, tree1)
        self.assertEqual(cache._instance_cache[M.repository.Tree], {
            'id1': tree1,
        })
        self.assertEqual(cache._query_cache[M.repository.Tree], {
            (('query_1', 'bar'),): 'id1',
            (('query_2', 'bar'),): 'id1',
            (('query_3', 'bar'),): 'id1',
        })

    @mock.patch('bson.ObjectId')
    def test_pruning_none(self, obj_id):
        obj_id.side_effect = ['id1', 'id2', 'id3']
        cache = M.repository.ModelCache(max_queries=3, max_instances=2)
        # ensure cache doesn't store None instances
        cache.set(M.repository.Tree, {'query_1': 'bar'}, None)
        cache.set(M.repository.Tree, {'query_2': 'bar'}, None)
        cache.set(M.repository.Tree, {'query_3': 'bar'}, None)
        self.assertEqual(cache._instance_cache[M.repository.Tree], {})
        self.assertEqual(cache._query_cache[M.repository.Tree], {
            (('query_1', 'bar'),): None,
            (('query_2', 'bar'),): None,
            (('query_3', 'bar'),): None,
        })

    @mock.patch('allura.model.repository.session')
    @mock.patch.object(M.repository.Tree.query, 'get')
    def test_pruning_query_flush(self, tr_get, session):
        cache = M.repository.ModelCache(max_queries=3, max_instances=2)
        # ensure cache doesn't store None instances
        tree1 = mock.Mock(name='tree1',
                          spec=['_id', '_val'], _id='tree1', val='bar')
        tree2 = mock.Mock(name='tree2',
                          spec=['_id', '_val'], _id='tree2', val='fuz')
        tr_get.return_value = tree2
        cache.set(M.repository.Tree, {'_id': 'tree1'}, tree1)
        cache.set(M.repository.Tree, {'_id': 'tree2'}, tree2)
        cache.get(M.repository.Tree, {'query_1': 'tree2'})
        cache.get(M.repository.Tree, {'query_2': 'tree2'})
        cache.get(M.repository.Tree, {'query_3': 'tree2'})
        self.assertEqual(cache._query_cache[M.repository.Tree], {
            (('query_1', 'tree2'),): 'tree2',
            (('query_2', 'tree2'),): 'tree2',
            (('query_3', 'tree2'),): 'tree2',
        })
        self.assertEqual(cache._instance_cache[M.repository.Tree], {
            'tree1': tree1,
            'tree2': tree2,
        })
        self.assertEqual(session.call_args_list,
                         [mock.call(tree1), mock.call(tree2)])
        self.assertEqual(session.return_value.flush.call_args_list,
                         [mock.call(tree1), mock.call(tree2)])
        assert not session.return_value.expunge.called

    @mock.patch('allura.model.repository.session')
    def test_pruning_instance_flush(self, session):
        cache = M.repository.ModelCache(max_queries=3, max_instances=2)
        # ensure cache doesn't store None instances
        tree1 = mock.Mock(spec=['_id', '_val'], _id='tree1', val='bar')
        tree2 = mock.Mock(spec=['_id', '_val'], _id='tree2', val='fuz')
        tree3 = mock.Mock(spec=['_id', '_val'], _id='tree3', val='qux')
        cache.set(M.repository.Tree, {'_id': 'tree1'}, tree1)
        cache.set(M.repository.Tree, {'_id': 'tree2'}, tree2)
        cache.set(M.repository.Tree, {'_id': 'tree3'}, tree3)
        self.assertEqual(cache._query_cache[M.repository.Tree], {
            (('_id', 'tree1'),): 'tree1',
            (('_id', 'tree2'),): 'tree2',
            (('_id', 'tree3'),): 'tree3',
        })
        self.assertEqual(cache._instance_cache[M.repository.Tree], {
            'tree2': tree2,
            'tree3': tree3,
        })
        session.assert_called_once_with(tree1)
        session.return_value.flush.assert_called_once_with(tree1)
        session.return_value.expunge.assert_called_once_with(tree1)


class TestMergeRequest:

    def setup_method(self, method):
        setup_basic_test()
        setup_global_objects()
        self.mr = M.MergeRequest(
            app_config=mock.Mock(_id=ObjectId()),
            downstream={'commit_id': '12345'},
            request_number=1,

        )
        self._set_mr_mock_attrs(self.mr)

    def _set_mr_mock_attrs(self, mr):
        mr.app = mock.Mock(forkable=True, url='/mock-app-url/', activity_name='code merge', activity_url='/fake/url', activity_extras={}, node_id=None)
        mr.app.repo.commit.return_value = mock.Mock(_id='09876')
        mr.merge_allowed = mock.Mock(return_value=True)
        mr.discussion_thread = mock.Mock()

    def _reload_mr_from_db(self, mr):
        session(mr).refresh(mr)
        mr = M.MergeRequest.query.get(_id=mr._id)
        self._set_mr_mock_attrs(mr)
        return mr

    def test_can_merge_cache_key(self):
        key = self.mr.can_merge_cache_key()
        assert key == '12345-09876'

    def test_get_can_merge_cache(self):
        key = self.mr.can_merge_cache_key()
        assert self.mr.get_can_merge_cache() is None
        self.mr.can_merge_cache[key] = True
        assert self.mr.get_can_merge_cache() is True

        self.mr.can_merge_cache_key = lambda: '123-123'
        self.mr.can_merge_cache['123-123'] = False
        assert self.mr.get_can_merge_cache() is False

    def test_set_can_merge_cache(self):
        key = self.mr.can_merge_cache_key()
        assert self.mr.can_merge_cache == {}
        self.mr.set_can_merge_cache(True)
        assert self.mr.can_merge_cache == {key: True}

        self.mr.can_merge_cache_key = lambda: '123-123'
        self.mr.set_can_merge_cache(False)
        assert self.mr.can_merge_cache == {key: True, '123-123': False}

    def test_can_merge_merged(self):
        self.mr.status = 'merged'
        assert self.mr.can_merge() is True

    @mock.patch('allura.tasks.repo_tasks.can_merge', autospec=True)
    def test_can_merge_cached(self, can_merge_task):
        # this test has to flush `mr` to the db and then reload it after changes, because set_can_merge_cache
        # does a $set to the db and doesn't update the in-memory copy
        session(self.mr).flush(self.mr)

        self.mr.set_can_merge_cache(False)
        self.mr = self._reload_mr_from_db(self.mr)
        assert self.mr.can_merge() is False

        self.mr.set_can_merge_cache(True)
        self.mr = self._reload_mr_from_db(self.mr)
        assert self.mr.can_merge() is True
        assert can_merge_task.post.call_count == 0

    @mock.patch('allura.tasks.repo_tasks.can_merge', autospec=True)
    def test_can_merge_not_cached(self, can_merge_task):
        assert self.mr.can_merge() is None
        can_merge_task.post.assert_called_once_with(self.mr._id)

    @mock.patch('allura.tasks.repo_tasks.can_merge', autospec=True)
    def test_can_merge_disabled(self, can_merge_task):
        self.mr.merge_allowed.return_value = False
        assert self.mr.can_merge() is None
        assert can_merge_task.post.call_count == 0

    @mock.patch('allura.tasks.repo_tasks.merge', autospec=True)
    def test_merge(self, merge_task):
        self.mr.merge_task_status = lambda: None
        self.mr.merge()
        merge_task.post.assert_called_once_with(self.mr._id)

        merge_task.reset_mock()
        self.mr.merge_task_status = lambda: 'ready'
        self.mr.merge()
        assert merge_task.post.called is False

    def test_merge_task_status(self):
        from allura.tasks import repo_tasks
        assert self.mr.merge_task_status() is None
        repo_tasks.merge.post(self.mr._id)
        assert self.mr.merge_task_status() == 'ready'
        M.MonQTask.run_ready()
        assert self.mr.merge_task_status() == 'complete'

    def test_can_merge_task_status(self):
        from allura.tasks import repo_tasks
        assert self.mr.can_merge_task_status() is None
        repo_tasks.can_merge.post(self.mr._id)
        assert self.mr.can_merge_task_status() == 'ready'
        with mock.patch('allura.model.repository.MergeRequest.set_can_merge_cache'):
            M.MonQTask.run_ready()
        assert self.mr.can_merge_task_status() == 'complete'
