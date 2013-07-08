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

from nose.tools import assert_equals
from mock import Mock, MagicMock, patch

from allura import model as M
from allura.lib.utils import TruthyCallable
from allura.lib.plugin import ProjectRegistrationProvider


class TestProjectRegistrationProvider(object):

    def setUp(self):
        self.provider = ProjectRegistrationProvider()

    @patch('allura.lib.security.has_access')
    def test_validate_project_15char_user(self, has_access):
        has_access.return_value = TruthyCallable(lambda: True)
        nbhd = M.Neighborhood()
        self.provider.validate_project(
            neighborhood=nbhd,
            shortname='u/' + ('a' * 15),
            project_name='15 char username',
            user=MagicMock(),
            user_project=True,
            private_project=False,
        )

    def test_suggest_name(self):
        f = self.provider.suggest_name
        assert_equals(f('A More Than Fifteen Character Name', Mock()),
                'amorethanfifteencharactername')

    def test_valid_project_shortname(self):
        f = self.provider.valid_project_shortname
        p = Mock()
        valid = (True, None)
        invalid = (False,
                'Please use only letters, numbers, and dashes '
                '3-15 characters long.')
        assert_equals(f('thisislegit', p), valid)
        assert_equals(f('not valid', p), invalid)
        assert_equals(f('this-is-valid-but-too-long', p), invalid)
        assert_equals(f('this is invalid and too long', p), invalid)

    def test_allowed_project_shortname(self):
        allowed = valid = (True, None)
        invalid = (False, 'invalid')
        taken = (False, 'This project name is taken.')
        cases = [
                (valid, False, allowed),
                (invalid, False, invalid),
                (valid, True, taken),
            ]
        p = Mock()
        vps = self.provider.valid_project_shortname = Mock()
        nt = self.provider._name_taken = Mock()
        f = self.provider.allowed_project_shortname
        for vps_v, nt_v, result in cases:
            vps.return_value = vps_v
            nt.return_value = nt_v
            assert_equals(f('project', p), result)
