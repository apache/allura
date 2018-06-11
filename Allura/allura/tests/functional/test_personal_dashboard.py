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

from nose.tools import assert_equal, assert_in

from allura.tests import TestController


class TestPersonalDashboard(TestController):

    def test_profile(self):
        r = self.app.get('/dashboard')
        assert_equal('Test Admin / Dashboard', r.html.find('h1', 'project_title').text)
        sections = set([c for s in r.html.findAll(None, 'profile-section') for c in s['class'].split()])
        assert_in('tickets', sections)
        assert_in('projects', sections)
        assert_in('merge_requests', sections)
        assert_in('followers', sections)
