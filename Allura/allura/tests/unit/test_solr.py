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

from allura.lib.solr import Solr

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
