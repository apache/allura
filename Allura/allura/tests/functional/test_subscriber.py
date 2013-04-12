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
from allura.model.notification import Mailbox
from allura import model as M


class TestSubscriber(TestController):

    @td.with_user_project('test-admin')
    @td.with_wiki
    def test_add_subscriber(self):

        response = self.app.get("/nf/admin/add_subscribers")
        assert "<h1>Add Subscribers to Artifact</h1>" in response

        self.app.post("/nf/admin/add_subscribers", params=dict(
            for_user="root",
            artifact_url="http://localhost:8080/u/test-admin/wiki/Home/"))

        assert 1 == Mailbox.query.find(dict(
            user_id=M.User.by_username("root")._id,
            artifact_url="/u/test-admin/wiki/Home/")).count()
