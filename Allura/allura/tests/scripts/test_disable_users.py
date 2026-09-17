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

import pytest
from ming.odm import ThreadLocalODMSession

from allura import model as M
from allura.scripts.disable_users import DisableUsers
from alluratest.controller import setup_basic_test, setup_global_objects


class TestDisableUsers:
    def setup_method(self):
        setup_basic_test()
        setup_global_objects()

    @pytest.mark.parametrize('message', ['', 'Custom reason 100%', 'Disabling user due to automatically detected spam'])
    def test_event_type(self, message):
        user = M.User.by_username('test-user')
        DisableUsers.disable_users([user.username], message)
        ThreadLocalODMSession.flush_all()

        assert user.disabled
        entries = M.AuditLog.for_user(user).sort('_id').all()
        assert len(entries) == (2 if message else 1)
        for entry in entries:
            assert entry.event_type == 'account.disabled'
            assert M.AuditLog.decr(entry.message_encrypted) == entry.message
        if message:
            assert entries[-1].message.endswith(message)
