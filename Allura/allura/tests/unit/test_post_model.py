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

from tg import tmpl_context as c

from allura.lib import helpers as h
from allura import model as M
from allura.tests.unit import WithDatabase
from allura.tests.unit import patches
from allura.tests.unit.factories import create_post


class TestPostModel(WithDatabase):
    patches = [patches.fake_app_patch,
               patches.disable_notifications_patch]

    def setup_method(self, method):
        super().setup_method(method)
        self.post = create_post('mypost')

    def test_that_it_is_pending_by_default(self):
        assert self.post.status == 'pending'

    def test_that_it_can_be_approved(self):
        with h.push_config(c, user=M.User()):
            self.post.approve()
        assert self.post.status == 'ok'

    def test_activity_extras(self):
        self.post.text = """\
This is a **bold thing**, 40 chars here.

* Here's the first item in our list.
* And here's the second item.""" + ','.join(map(str, list(range(200))))
        assert 'allura_id' in self.post.activity_extras
        summary = self.post.activity_extras['summary']
        assert summary.startswith("This is a bold thing, 40 chars here. Here's the first item in our list. "
                                  "And here's the second item."), summary  # no formatting/HTML
        assert summary.endswith('125,126,127...'), summary  # it gets truncated
