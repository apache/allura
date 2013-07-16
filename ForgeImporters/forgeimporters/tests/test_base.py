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

from unittest import TestCase

from formencode import Invalid
import mock

from .. import base


def ep(name, source=None):
    mep = mock.Mock(name='mock_ep')
    mep.name = name
    mep.load.return_value.source = source
    mep.lv = mep.load.return_value.return_value
    return mep


class TestProjectImporterDispatcher(TestCase):
    @mock.patch('forgeimporters.base.iter_entry_points')
    def test_lookup(self, iep):
        eps = iep.return_value = [ep('ep1', 'first'), ep('ep2', 'second')]
        result = base.ProjectImporterDispatcher()._lookup('source', 'rest1', 'rest2')
        self.assertEqual(result, (eps[0].lv, ('rest1', 'rest2')))
        iep.assert_called_once_with('allura.project_importers', 'source')


class TestProjectImporter(TestCase):
    @mock.patch('forgeimporters.base.iter_entry_points')
    def test_tool_importers(self, iep):
        eps = iep.return_value = [ep('ep1', 'foo'), ep('ep2', 'bar'), ep('ep3', 'foo')]
        pi = base.ProjectImporter()
        pi.source = 'foo'
        self.assertEqual(pi.tool_importers, {'ep1': eps[0].lv, 'ep3': eps[2].lv})
        iep.assert_called_once_with('allura.importers')


class TestImporter(TestCase):
    class TI1(base.ToolImporter):
        target_app = mock.Mock(tool_label='foo', tool_description='foo_desc')

    class TI2(base.ToolImporter):
        target_app = mock.Mock(tool_label='foo', tool_description='foo_desc')
        tool_label = 'bar'
        tool_description = 'bar_desc'

    def test_tool_label(self):
        self.assertEqual(self.TI1().tool_label, 'foo')
        self.assertEqual(self.TI2().tool_label, 'bar')

    def test_tool_description(self):
        self.assertEqual(self.TI1().tool_description, 'foo_desc')
        self.assertEqual(self.TI2().tool_description, 'bar_desc')


class TestToolsValidator(TestCase):
    def setUp(self):
        self.tv = base.ToolsValidator('good-source')

    @mock.patch('forgeimporters.base.iter_entry_points')
    def test_empty(self, iep):
        self.assertEqual(self.tv.to_python(''), [])
        self.assertEqual(iep.call_count, 0)

    @mock.patch('forgeimporters.base.iter_entry_points')
    def test_no_ep(self, iep):
        eps = iep.return_value.next.side_effect = StopIteration
        with self.assertRaises(Invalid) as cm:
            self.tv.to_python('my-value')
        self.assertEqual(cm.exception.msg, 'Invalid tool selected: my-value')
        iep.assert_called_once_with('allura.importers', 'my-value')

    @mock.patch('forgeimporters.base.iter_entry_points')
    def test_bad_source(self, iep):
        eps = iep.return_value.next.side_effect = [ep('ep1', 'bad-source'), ep('ep2', 'good-source')]
        with self.assertRaises(Invalid) as cm:
            self.tv.to_python('my-value')
        self.assertEqual(cm.exception.msg, 'Invalid tool selected: my-value')
        iep.assert_called_once_with('allura.importers', 'my-value')

    @mock.patch('forgeimporters.base.iter_entry_points')
    def test_multiple(self, iep):
        eps = iep.return_value.next.side_effect = [ep('ep1', 'bad-source'), ep('ep2', 'good-source'), ep('ep3', 'bad-source')]
        with self.assertRaises(Invalid) as cm:
            self.tv.to_python(['value1', 'value2', 'value3'])
        self.assertEqual(cm.exception.msg, 'Invalid tools selected: value1, value3')
        self.assertEqual(iep.call_args_list, [
                mock.call('allura.importers', 'value1'),
                mock.call('allura.importers', 'value2'),
                mock.call('allura.importers', 'value3'),
            ])

    @mock.patch('forgeimporters.base.iter_entry_points')
    def test_valid(self, iep):
        eps = iep.return_value.next.side_effect = [ep('ep1', 'good-source'), ep('ep2', 'good-source'), ep('ep3', 'bad-source')]
        self.assertEqual(self.tv.to_python(['value1', 'value2']), [eps[0].lv, eps[1].lv])
        self.assertEqual(iep.call_args_list, [
                mock.call('allura.importers', 'value1'),
                mock.call('allura.importers', 'value2'),
            ])
