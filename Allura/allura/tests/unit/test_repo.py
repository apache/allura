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

import datetime
import unittest

import six
from mock import patch, Mock, MagicMock, call

from tg import tmpl_context as c

from allura import model as M
from allura.controllers.repository import topo_sort
from allura.model.repository import zipdir, prefix_paths_union
from allura.model.repo_refresh import (
    _group_commits,
)


class TestTopoSort(unittest.TestCase):

    def test_commit_dates_out_of_order(self):
        """Commits should be sorted by their parent/child relationships,
        regardless of the date on the commit.
        """
        head_ids = ['dev', 'master']
        parents = {
            'dev':        ['dev@{1}'],
            'dev@{1}':    ['master'],
            'master':     ['master@{1}'],
            'master@{1}': ['master@{2}'],
            'master@{2}': ['master@{3}'],
            'master@{3}': []}
        children = {
            'master@{3}': ['master@{2}'],
            'master@{2}': ['master@{1}'],
            'master@{1}': ['master'],
            'master':     ['dev@{1}'],
            'dev@{1}':    ['dev'],
            'dev':        []}
        dates = {
            'dev@{1}':    datetime.datetime(2012, 1, 1),
            'master@{3}': datetime.datetime(2012, 2, 1),
            'master@{2}': datetime.datetime(2012, 3, 1),
            'master@{1}': datetime.datetime(2012, 4, 1),
            'master':     datetime.datetime(2012, 5, 1),
            'dev':        datetime.datetime(2012, 6, 1)}
        result = topo_sort(children, parents, dates, head_ids)
        self.assertEqual(list(result), ['dev', 'dev@{1}', 'master',
                                        'master@{1}', 'master@{2}', 'master@{3}'])


def tree(name, id, trees=None, blobs=None):
    t = Mock(tree_ids=[], blob_ids=[], other_ids=[])
    t.name = name
    t.id = id
    t._id = id
    if trees is not None:
        t.tree_ids = trees
    if blobs is not None:
        t.blob_ids = blobs
    return t


def blob(name, id):
    b = Mock()
    b.name = name
    b.id = id
    return b


class TestTree(unittest.TestCase):

    @patch('allura.model.repository.Tree.__getitem__')
    def test_get_obj_by_path(self, getitem):
        tree = M.repository.Tree()
        # test with relative path
        tree.get_obj_by_path('some/path/file.txt')
        getitem.assert_called_with('some')
        getitem().__getitem__.assert_called_with('path')
        getitem().__getitem__().__getitem__.assert_called_with('file.txt')
        # test with absolute path
        tree.get_obj_by_path('/some/path/file.txt')
        getitem.assert_called_with('some')
        getitem().__getitem__.assert_called_with('path')
        getitem().__getitem__().__getitem__.assert_called_with('file.txt')


class TestBlob(unittest.TestCase):

    def test_pypeline_view(self):
        blob = M.repository.Blob(MagicMock(), 'INSTALL.mdown', 'blob1')
        assert blob.has_pypeline_view is True

    def test_has_html_view_text_mime(self):
        blob = M.repository.Blob(MagicMock(), 'INSTALL', 'blob1')
        blob.content_type = 'text/plain'
        assert blob.has_html_view is True

    def test_has_html_view_text_ext(self):
        blob = M.repository.Blob(MagicMock(), 'INSTALL.txt', 'blob1')
        blob.content_type = 'foo/bar'
        assert blob.has_html_view is True

    def test_has_html_view_text_contents(self):
        blob = M.repository.Blob(MagicMock(), 'INSTALL', 'blob1')
        blob.content_type = 'foo/bar'
        blob.text = b'hello world, this is text here'
        assert blob.has_html_view is True

    def test_has_html_view_bin_ext(self):
        blob = M.repository.Blob(MagicMock(), 'INSTALL.zip', 'blob1')
        assert blob.has_html_view is False

    def test_has_html_view_bin_content(self):
        blob = M.repository.Blob(MagicMock(), 'myfile', 'blob1')
        blob.content_type = 'whatever'
        blob.text = b'\0\0\0\0'
        assert blob.has_html_view is False

    def test_has_html_view__local_setting_override_bin(self):
        blob = M.repository.Blob(MagicMock(), 'myfile.dat', 'blob1')
        blob.content_type = 'whatever'
        blob.text = b'\0\0\0\0'
        blob.repo._additional_viewable_extensions = ['.dat']
        assert blob.has_html_view is True


class TestCommit(unittest.TestCase):

    def test_activity_extras(self):
        commit = M.repository.Commit()
        commit.shorthand_id = MagicMock(return_value='abcdef')
        commit.message = 'commit msg'
        self.assertIn('allura_id', commit.activity_extras)
        self.assertEqual(commit.activity_extras['summary'], commit.summary)

    def test_get_path_no_create(self):
        commit = M.repository.Commit()
        commit.get_tree = MagicMock()
        commit.get_path('foo/', create=False)
        commit.get_tree.assert_called_with(False)
        commit.get_tree().__getitem__.assert_called_with('foo')
        self.assertNotIn(call(''), commit.get_tree().__getitem__.call_args_list)

    def test_get_tree_no_create(self):
        c.model_cache = Mock()
        c.model_cache.get.return_value = None
        commit = M.repository.Commit()
        commit.repo = Mock()

        commit.tree_id = None
        tree = commit.get_tree(create=False)
        assert not commit.repo.compute_tree_new.called
        assert not c.model_cache.get.called
        assert tree is None

        commit.tree_id = 'tree'
        tree = commit.get_tree(create=False)
        assert not commit.repo.compute_tree_new.called
        c.model_cache.get.assert_called_with(M.repository.Tree, dict(_id='tree'))
        assert tree is None

        _tree = Mock()
        c.model_cache.get.return_value = _tree
        tree = commit.get_tree(create=False)
        _tree.set_context.assert_called_with(commit)
        assert tree == _tree

    @patch.object(M.repository.Tree.query, 'get')
    def test_get_tree_create(self, tree_get):
        c.model_cache = Mock()
        c.model_cache.get.return_value = None
        commit = M.repository.Commit()
        commit.repo = Mock()

        commit.repo.compute_tree_new.return_value = None
        commit.tree_id = None
        tree = commit.get_tree()
        commit.repo.compute_tree_new.assert_called_once_with(commit)
        assert not c.model_cache.get.called
        assert not tree_get.called
        assert tree is None

        commit.repo.compute_tree_new.reset_mock()
        commit.repo.compute_tree_new.return_value = 'tree'
        _tree = Mock()
        c.model_cache.get.return_value = _tree
        tree = commit.get_tree()
        commit.repo.compute_tree_new.assert_called_once_with(commit)
        assert not tree_get.called
        c.model_cache.get.assert_called_once_with(
            M.repository.Tree, dict(_id='tree'))
        _tree.set_context.assert_called_once_with(commit)
        assert tree == _tree

        commit.repo.compute_tree_new.reset_mock()
        c.model_cache.get.reset_mock()
        commit.tree_id = 'tree2'
        tree = commit.get_tree()
        assert not commit.repo.compute_tree_new.called
        assert not tree_get.called
        c.model_cache.get.assert_called_once_with(
            M.repository.Tree, dict(_id='tree2'))
        _tree.set_context.assert_called_once_with(commit)
        assert tree == _tree

        commit.repo.compute_tree_new.reset_mock()
        c.model_cache.get.reset_mock()
        c.model_cache.get.return_value = None
        tree_get.return_value = _tree
        tree = commit.get_tree()
        c.model_cache.get.assert_called_once_with(
            M.repository.Tree, dict(_id='tree2'))
        commit.repo.compute_tree_new.assert_called_once_with(commit)
        assert commit.tree_id == 'tree'
        tree_get.assert_called_once_with(_id='tree')
        c.model_cache.set.assert_called_once_with(
            M.repository.Tree, dict(_id='tree'), _tree)
        _tree.set_context.assert_called_once_with(commit)
        assert tree == _tree

    def test_tree_create(self):
        commit = M.repository.Commit()
        commit.get_tree = Mock()
        tree = commit.tree
        commit.get_tree.assert_called_with(create=True)


class TestZipDir(unittest.TestCase):

    @patch('allura.model.repository.Popen')
    @patch('allura.model.repository.tg')
    def test_popen_called(self, tg, popen):
        from subprocess import PIPE
        popen.return_value.communicate.return_value = 1, 2
        popen.return_value.returncode = 0
        tg.config = {'scm.repos.tarball.zip_binary': '/bin/zip'}
        src = '/fake/path/to/repo'
        zipfile = '/fake/zip/file.tmp'
        zipdir(src, zipfile)
        popen.assert_called_once_with(
            ['/bin/zip', '-y', '-q', '-r', zipfile, b'repo'],
            cwd='/fake/path/to', stdout=PIPE, stderr=PIPE)
        popen.reset_mock()
        src = '/fake/path/to/repo/'
        zipdir(src, zipfile, exclude='file.txt')
        popen.assert_called_once_with(
            ['/bin/zip', '-y', '-q', '-r',
             zipfile, b'repo', '-x', 'file.txt'],
            cwd='/fake/path/to', stdout=PIPE, stderr=PIPE)

    @patch('allura.model.repository.Popen')
    @patch('allura.model.repository.tg')
    def test_exception_logged(self, tg, popen):
        tg.config = {'scm.repos.tarball.zip_binary': '/bin/zip'}
        popen.return_value.communicate.return_value = 1, 2
        popen.return_value.returncode = 1
        src = '/fake/path/to/repo'
        zipfile = '/fake/zip/file.tmp'
        with self.assertRaises(Exception) as cm:
            zipdir(src, zipfile)
        emsg = str(cm.exception)
        self.assertIn(
            "Command: " +
            ("['/bin/zip', '-y', '-q', '-r', '/fake/zip/file.tmp', b'repo'] " if six.PY3 else
             "[u'/bin/zip', u'-y', u'-q', u'-r', u'/fake/zip/file.tmp', 'repo'] ") +
            "returned non-zero exit code 1", emsg)
        self.assertTrue("STDOUT: 1" in emsg)
        self.assertTrue("STDERR: 2" in emsg)


class TestPrefixPathsUnion(unittest.TestCase):

    def test_disjoint(self):
        a = {'a1', 'a2', 'a3'}
        b = {'b1', 'b1/foo', 'b2'}
        self.assertEqual(prefix_paths_union(a, b), set())

    def test_exact(self):
        a = {'a1', 'a2', 'a3'}
        b = {'b1', 'a2', 'a3'}
        self.assertEqual(prefix_paths_union(a, b), {'a2', 'a3'})

    def test_prefix(self):
        a = {'a1', 'a2', 'a3'}
        b = {'b1', 'a2/foo', 'b3/foo'}
        self.assertEqual(prefix_paths_union(a, b), {'a2'})


class TestGroupCommits:

    def setup_method(self, method):
        self.repo = Mock()
        self.repo.symbolics_for_commit.return_value = ([], [])

    def test_no_branches(self):
        b, t = _group_commits(self.repo, ['3', '2', '1'])
        assert b == {'__default__': ['3', '2', '1']}
        assert t == {}

    def test_branches_and_tags(self):
        self.repo.symbolics_for_commit.side_effect = [
            (['master'], ['v1.1']),
            ([], []),
            ([], []),
        ]
        b, t = _group_commits(self.repo, ['3', '2', '1'])
        assert b == {'master': ['3', '2', '1']}
        assert t == {'v1.1': ['3', '2', '1']}

    def test_multiple_branches(self):
        self.repo.symbolics_for_commit.side_effect = [
            (['master'], ['v1.1']),
            ([], ['v1.0']),
            (['test1', 'test2'], []),
        ]
        b, t = _group_commits(self.repo, ['3', '2', '1'])
        assert b == {'master': ['3', '2'],
                     'test1': ['1'],
                     'test2': ['1']}
        assert t == {'v1.1': ['3'],
                     'v1.0': ['2', '1']}
