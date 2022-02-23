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

from allura.tests import TestController
from allura.tests import decorators as td


class TestToolListController(TestController):

    @td.with_wiki
    @td.with_tool('test', 'Wiki', 'wiki2')
    def test_default(self):
        """Test that list page contains a link to all tools of that type."""
        r = self.app.get('/p/test/_list/wiki')
        content = r.html.find('div', id='content_base')
        assert content.find('a', dict(href='/p/test/wiki/')), r
        assert content.find('a', dict(href='/p/test/wiki2/')), r

    @td.with_wiki
    @td.with_tool('test', 'Wiki', 'wiki2')
    def test_paging(self):
        """Test that list page handles paging correctly."""
        r = self.app.get('/p/test/_list/wiki?limit=1&page=0')
        content = r.html.find('div', id='content_base')
        assert content.find('a', dict(href='/p/test/wiki/')), r
        assert not content.find('a', dict(href='/p/test/wiki2/')), r
        r = self.app.get('/p/test/_list/wiki?limit=1&page=1')
        content = r.html.find('div', id='content_base')
        assert not content.find('a', dict(href='/p/test/wiki/')), r
        assert content.find('a', dict(href='/p/test/wiki2/')), r

    def test_missing_path(self):
        self.app.get('/p/test/_list/', status=404)
