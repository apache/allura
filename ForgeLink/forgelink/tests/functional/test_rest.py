# coding: utf-8

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

from nose.tools import assert_equal
from allura.tests import decorators as td
from alluratest.controller import TestRestApiBase


class TestLinkApi(TestRestApiBase):

    @td.with_link
    def test_rest_link(self):
        r = self.api_get(u'/rest/p/test/link'.encode('utf-8'))
        assert_equal(r.json['url'], None)

        data = {'url': 'http://google.com'}
        r = self.api_post(u'/rest/p/test/link'.encode('utf-8'), **data)
        assert_equal(r.json['url'], 'http://google.com')

        data = {'url': 'http://yahoo.com'}
        self.api_post(u'/rest/p/test/link'.encode('utf-8'), **data)
        r = self.api_get(u'/rest/p/test/link'.encode('utf-8'))
        assert_equal(r.json['url'], 'http://yahoo.com')
