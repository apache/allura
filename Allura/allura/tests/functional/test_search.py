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

from mock import patch
from allura.tests import TestController


class TestSearch(TestController):

    @patch('allura.lib.search.search')
    def test_global_search_controller(self, search):
        self.app.get('/gsearch/')
        assert not search.called, search.called
        self.app.get('/gsearch/', params=dict(q='Root'))
        assert search.called, search.called

    def test_project_search_controller(self):
        self.app.get('/search/')
        self.app.get('/search/', params=dict(q='Root'))
