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

from __future__ import absolute_import
from alluratest.controller import setup_basic_test
from allura.websetup.bootstrap import clear_all_database_tables


def setUp(self):
    setup_basic_test()


class MockPatchTestCase(object):
    patches = []

    def setUp(self):
        self._patch_instances = [patch_fn(self) for patch_fn in self.patches]
        for patch_instance in self._patch_instances:
            patch_instance.__enter__()

    def tearDown(self):
        for patch_instance in self._patch_instances:
            patch_instance.__exit__()


class WithDatabase(MockPatchTestCase):

    def setUp(self):
        super(WithDatabase, self).setUp()
        clear_all_database_tables()
