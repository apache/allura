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

from allura import model as M
from allura.tests import decorators as td
from alluratest.controller import setup_basic_test, setup_global_objects


class TestActivityObject_Functional:
    # NOTE not for unit tests, this class sets up all the junk

    def setup_method(self, method):
        setup_basic_test()
        setup_global_objects()

    @td.with_wiki
    def test_has_activity_access_app_config(self):
        # AppConfig inherits ActivityObject but may have different attributes
        # than other ActivityObjects that are mostly artifacts

        p = M.Project.query.get(shortname='test')
        wiki_app = p.app_instance('wiki')
        app_config = wiki_app.config

        assert (bool(app_config.has_activity_access('read', user=M.User.anonymous(), activity=None)) ==
                     True)