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

import json

from allura.tests import TestController
from forgesvn.tests import with_svn


class TestSVNAuth(TestController):

    @with_svn
    def test_refresh_repo(self):
        r = self.app.get('/auth/refresh_repo')
        assert r.text == 'No repo specified'

        r = self.app.get('/auth/refresh_repo/p/gbalksdfh')
        assert r.text == 'No project at /p/gbalksdfh'

        r = self.app.get('/auth/refresh_repo/p/test')
        assert r.text == '/p/test does not include a repo mount point'

        r = self.app.get('/auth/refresh_repo/p/test/blah/')
        assert r.text == 'Cannot find repo at /p/test/blah'

        r = self.app.get('/auth/refresh_repo/p/test/src/')
        assert (r.text ==
                     '<Repository /tmp/svn/p/test/src> refresh queued.\n')


class TestSVNUserPermissions(TestController):
    allow = dict(allow_read=True, allow_write=True, allow_create=True)
    read = dict(allow_read=True, allow_write=False, allow_create=False)
    disallow = dict(allow_read=False, allow_write=False, allow_create=False)

    @with_svn
    def test_list_repos(self):
        r = self.app.get('/auth/repo_permissions',
                         params=dict(username='test-admin'), status=200)
        assert json.loads(r.text) == {"allow_write": [
            '/svn/test/src',
        ]}
