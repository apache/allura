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
import tempfile

import mock

from bson import ObjectId

from allura.lib.spam.stopforumspamfilter import StopForumSpamSpamFilter


class TestStopForumSpam:

    def setup_method(self, method):
        self.content = 'spåm text'

        self.artifact = mock.Mock()
        self.artifact.project_id = ObjectId()
        self.artifact.ref = None

        with tempfile.NamedTemporaryFile('w') as f:
            f.write('''"1.1.1.1","2","2018-01-22 10:56:29"
"1.2.3.4","42","2017-09-24 18:33:00"
"4.3.2.1","1","2017-09-28 14:03:53"''')
            f.flush()
            self.sfs = StopForumSpamSpamFilter({'spam.stopforumspam.ip_addr_file': f.name})

    @mock.patch('allura.lib.spam.stopforumspamfilter.request')
    def test_check(self, request):
        request.remote_addr = '1.2.3.4'
        assert True == self.sfs.check(self.content, artifact=self.artifact)

        request.remote_addr = '1.1.1.1'
        assert False == self.sfs.check(self.content, artifact=self.artifact)

        request.remote_addr = None  # e.g. from background task processing inbound email
        assert False == self.sfs.check(self.content, artifact=self.artifact)
