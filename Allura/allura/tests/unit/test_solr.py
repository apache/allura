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

import unittest
import mock
from nose.tools import assert_equal

from allura.lib.solr import Solr
from allura.lib.search import solarize

class TestSolr(unittest.TestCase):
    @mock.patch('allura.lib.solr.pysolr')
    def setUp(self, pysolr):
        self.solr = Solr('server', commit=False, commitWithin='10000')

    @mock.patch('allura.lib.solr.pysolr')
    def test_add(self, pysolr):
        s = self.solr
        s.add('foo', commit=True, commitWithin=None)
        pysolr.Solr.add.assert_called_once_with(s, 'foo', commit=True,
                commitWithin=None)
        pysolr.reset_mock()
        s.add('bar', somekw='value')
        pysolr.Solr.add.assert_called_once_with(s, 'bar', commit=False,
                commitWithin='10000', somekw='value')

    @mock.patch('allura.lib.solr.pysolr')
    def test_delete(self, pysolr):
        s = self.solr
        s.delete('foo', commit=True)
        pysolr.Solr.delete.assert_called_once_with(s, 'foo', commit=True)
        pysolr.reset_mock()
        s.delete('bar', somekw='value')
        pysolr.Solr.delete.assert_called_once_with(s, 'bar', commit=False,
                somekw='value')

class TestSolarize(unittest.TestCase):

    def setUp(self):
        self.obj = mock.MagicMock()
        self.obj.index.return_value = {}

    def test_no_object(self):
        assert_equal(solarize(None), None)

    def test_empty_index(self):
        self.obj.index.return_value = None
        assert_equal(solarize(self.obj), None)

    def test_doc_without_text(self):
        assert_equal(solarize(self.obj), {'text': ''})

    def test_strip_markdown(self):
        self.obj.index.return_value = {'text': '# Header'}
        assert_equal(solarize(self.obj), {'text': 'Header'})

    def test_html_in_text(self):
        self.obj.index.return_value = {'text': '<script>alert(1)</script>'}
        assert_equal(solarize(self.obj), {'text': ''})
        self.obj.index.return_value = {'text': '&lt;script&gt;alert(1)&lt;/script&gt;'}
        assert_equal(solarize(self.obj), {'text': '&lt;script&gt;alert(1)&lt;/script&gt;'})
