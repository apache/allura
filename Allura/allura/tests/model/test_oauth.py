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


from ming.odm import ThreadLocalORMSession

from allura import model as M
from alluratest.controller import setup_basic_test, setup_global_objects


class TestOAuthModel:

    def setup_method(self):
        setup_basic_test()
        ThreadLocalORMSession.close_all()
        setup_global_objects()

    def test_upsert(self):
        admin = M.User.by_username('test-admin')
        user = M.User.by_username('test-user')
        name = 'test-token'
        token1 = M.OAuthConsumerToken.upsert(name, admin)
        token2 = M.OAuthConsumerToken.upsert(name, admin)
        token3 = M.OAuthConsumerToken.upsert(name, user)
        assert M.OAuthConsumerToken.query.find().count() == 2
        assert token1._id == token2._id
        assert token1._id != token3._id
