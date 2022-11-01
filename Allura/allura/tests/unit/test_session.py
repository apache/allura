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

import pymongo
import mock

from unittest import TestCase

import allura
from allura.tests import decorators as td
from allura.model.session import (
    IndexerSessionExtension,
    BatchIndexer,
    ArtifactSessionExtension,
    substitute_extensions,
)


def test_extensions_cm():
    session = mock.Mock(_kwargs=dict(extensions=[]))
    extension = mock.Mock()
    with substitute_extensions(session, [extension]) as sess:
        assert session.flush.call_count == 1
        assert session.close.call_count == 1
        assert sess == session
        assert sess._kwargs['extensions'] == [extension]
    assert session.flush.call_count == 2
    assert session.close.call_count == 2
    assert session._kwargs['extensions'] == []


def test_extensions_cm_raises():
    session = mock.Mock(_kwargs=dict(extensions=[]))
    extension = mock.Mock()
    with td.raises(ValueError):
        with substitute_extensions(session, [extension]) as sess:
            session.flush.side_effect = AttributeError
            assert session.flush.call_count == 1
            assert session.close.call_count == 1
            assert sess == session
            assert sess._kwargs['extensions'] == [extension]
            raise ValueError('test')
    assert session.flush.call_count == 1
    assert session.close.call_count == 1
    assert session._kwargs['extensions'] == []


def test_extensions_cm_flush_raises():
    session = mock.Mock(_kwargs=dict(extensions=[]))
    extension = mock.Mock()
    with td.raises(AttributeError):
        with substitute_extensions(session, [extension]) as sess:
            session.flush.side_effect = AttributeError
            assert session.flush.call_count == 1
            assert session.close.call_count == 1
            assert sess == session
            assert sess._kwargs['extensions'] == [extension]
    assert session.flush.call_count == 2
    assert session.close.call_count == 1
    assert session._kwargs['extensions'] == []


class TestSessionExtension(TestCase):

    def _mock_indexable(self, **kw):
        m = mock.Mock(**kw)
        m.__ming__ = mock.MagicMock()
        m.index_id.return_value = id(m)
        return m


class TestIndexerSessionExtension(TestSessionExtension):

    def setup_method(self, method):
        session = mock.Mock()
        self.ExtensionClass = IndexerSessionExtension
        self.extension = self.ExtensionClass(session)
        self.tasks = {'add': mock.Mock(), 'del': mock.Mock()}
        self.extension.TASKS = mock.Mock()
        self.extension.TASKS.get.return_value = self.tasks

    def test_flush(self):
        added = [self._mock_indexable(_id=i) for i in (1, 2, 3)]
        modified = [self._mock_indexable(_id=i) for i in (4, 5)]
        deleted = [self._mock_indexable(_id=i) for i in (6, 7)]
        self.extension.objects_added = added
        self.extension.objects_modified = modified
        self.extension.objects_deleted = deleted
        self.extension.after_flush()
        self.tasks['add'].post.assert_called_once_with([1, 2, 3, 4, 5])
        self.tasks['del'].post.assert_called_once_with(list(map(id, deleted)))

    def test_flush_skips_update(self):
        modified = [self._mock_indexable(_id=i) for i in range(5)]
        modified[1].should_update_index.return_value = False
        modified[4].should_update_index.return_value = False
        self.extension.objects_modified = modified
        self.extension.after_flush()
        self.tasks['add'].post.assert_called_once_with([0, 2, 3])

    def test_flush_skips_task_if_all_objects_filtered_out(self):
        modified = [self._mock_indexable(_id=i) for i in range(5)]
        for m in modified:
            m.should_update_index.return_value = False
        self.extension.objects_modified = modified
        self.extension.after_flush()
        assert self.tasks['add'].post.call_count == 0


class TestArtifactSessionExtension(TestSessionExtension):

    def setup_method(self, method):
        session = mock.Mock(disable_index=False)
        self.ExtensionClass = ArtifactSessionExtension
        self.extension = self.ExtensionClass(session)

    @mock.patch.object(allura.model.index.Shortlink, 'from_artifact')
    @mock.patch.object(allura.model.index.ArtifactReference, 'from_artifact')
    @mock.patch('allura.model.session.index_tasks')
    def test_flush_skips_update(self, index_tasks, ref_fa, shortlink_fa):
        modified = [self._mock_indexable(_id=i) for i in range(5)]
        modified[1].should_update_index.return_value = False
        modified[4].should_update_index.return_value = False
        ref_fa.side_effect = lambda obj: mock.Mock(_id=obj._id)
        self.extension.objects_modified = modified
        self.extension.after_flush()
        index_tasks.add_artifacts.post.assert_called_once_with([0, 2, 3])

    @mock.patch('allura.model.session.index_tasks')
    def test_flush_skips_task_if_all_objects_filtered_out(self, index_tasks):
        modified = [self._mock_indexable(_id=i) for i in range(5)]
        for m in modified:
            m.should_update_index.return_value = False
        self.extension.objects_modified = modified
        self.extension.after_flush()
        assert index_tasks.add_artifacts.post.call_count == 0


class TestBatchIndexer(TestCase):

    def setup_method(self, method):
        session = mock.Mock()
        self.extcls = BatchIndexer
        self.ext = self.extcls(session)

    def _mock_indexable(self, **kw):
        m = mock.Mock(**kw)
        m.index_id.return_value = id(m)
        return m

    @mock.patch('allura.model.ArtifactReference.query.find')
    def test_update_index(self, find):
        m = self._mock_indexable
        objs_deleted = [m(_id=i) for i in (1, 2, 3)]
        arefs = [m(_id=i) for i in (4, 5, 6)]
        find.return_value = [m(_id=i) for i in (7, 8, 9)]
        self.ext.update_index(objs_deleted, arefs)
        self.assertEqual(self.ext.to_delete,
                         {o.index_id() for o in objs_deleted})
        self.assertEqual(self.ext.to_add, {4, 5, 6})

        # test deleting something that was previously added
        objs_deleted += [m(_id=4)]
        find.return_value = [m(_id=4)]
        self.ext.update_index(objs_deleted, [])
        self.assertEqual(self.ext.to_delete,
                         {o.index_id() for o in objs_deleted})
        self.assertEqual(self.ext.to_add, {5, 6})

    @mock.patch('allura.model.session.index_tasks')
    def test_flush(self, index_tasks):
        objs_deleted = [self._mock_indexable(_id=i) for i in (1, 2, 3)]
        del_index_ids = {o.index_id() for o in objs_deleted}
        self.extcls.to_delete = del_index_ids
        self.extcls.to_add = {4, 5, 6}
        self.ext.flush()
        index_tasks.del_artifacts.post.assert_called_once_with(
            list(del_index_ids))
        index_tasks.add_artifacts.post.assert_called_once_with([4, 5, 6])
        self.assertEqual(self.ext.to_delete, set())
        self.assertEqual(self.ext.to_add, set())

    @mock.patch('allura.model.session.index_tasks')
    def test_flush_chunks_huge_lists(self, index_tasks):
        self.extcls.to_delete = set(range(100 * 1000 + 1))
        self.extcls.to_add = set(range(1000 * 1000 + 1))
        self.ext.flush()
        self.assertEqual(
            len(index_tasks.del_artifacts.post.call_args_list[0][0][0]),
            100 * 1000)
        self.assertEqual(
            len(index_tasks.del_artifacts.post.call_args_list[1][0][0]), 1)
        self.assertEqual(
            len(index_tasks.add_artifacts.post.call_args_list[0][0][0]),
            1000 * 1000)
        self.assertEqual(
            len(index_tasks.add_artifacts.post.call_args_list[1][0][0]), 1)
        self.assertEqual(self.ext.to_delete, set())
        self.assertEqual(self.ext.to_add, set())

    @mock.patch('allura.tasks.index_tasks')
    def test_flush_noop(self, index_tasks):
        self.ext.flush()
        self.assertEqual(0, index_tasks.del_artifacts.post.call_count)
        self.assertEqual(0, index_tasks.add_artifacts.post.call_count)
        self.assertEqual(self.ext.to_delete, set())
        self.assertEqual(self.ext.to_add, set())

    @mock.patch('allura.tasks.index_tasks')
    def test__post_too_large(self, index_tasks):
        def on_post(chunk):
            if len(chunk) > 1:
                e = pymongo.errors.InvalidDocument(
                    "BSON document too large (16906035 bytes) - the connected server supports BSON document sizes up to 16777216 bytes.")
                # ming injects a 2nd arg with the document, so we do too
                e.args = e.args + ("doc:  {'task_name': 'allura.tasks.index_tasks.add_artifacts', ........",)
                raise e
        index_tasks.add_artifacts.post.side_effect = on_post
        self.ext._post(index_tasks.add_artifacts, list(range(5)))
        expected = [
            mock.call([0, 1, 2, 3, 4]),
            mock.call([0, 1]),
            mock.call([0]),
            mock.call([1]),
            mock.call([2, 3, 4]),
            mock.call([2]),
            mock.call([3, 4]),
            mock.call([3]),
            mock.call([4])
        ]
        self.assertEqual(
            expected, index_tasks.add_artifacts.post.call_args_list)

    @mock.patch('allura.tasks.index_tasks')
    def test__post_other_error(self, index_tasks):
        def on_post(chunk):
            raise pymongo.errors.InvalidDocument("Cannot encode object...")
        index_tasks.add_artifacts.post.side_effect = on_post
        with td.raises(pymongo.errors.InvalidDocument):
            self.ext._post(index_tasks.add_artifacts, list(range(5)))
