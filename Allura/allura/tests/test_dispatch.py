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

app = None


class TestDispatch(TestController):

    validate_skip = True

    def test_dispatch(self):
        r = self.app.get('/dispatch/foo/')
        assert r.text == 'index foo', r
        r = self.app.get('/dispatch/foo/bar')
        assert r.text == "default(foo)(('bar',))", r
        self.app.get('/not_found', status=404)
        self.app.get('/dispatch/', status=404)
        # self.app.get('/hello/foo/bar', status=404)
