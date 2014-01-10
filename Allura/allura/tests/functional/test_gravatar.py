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

from urlparse import urlparse, parse_qs

from allura.tests import TestController
import allura.lib.gravatar as gravatar


class TestGravatar(TestController):

    def test_id(self):
        email = 'Wolf@example.com'
        expected_id = 'd3514940ac1b2051c8aa42970d17e3fe'
        actual_id = gravatar.id(email)
        assert expected_id == actual_id

    def test_unicode_id(self):
        email = u'Vin\u00EDcius@example.com'
        expected_id = 'e00968255d68523b034a6a39c522efdb'
        actual_id = gravatar.id(email)
        assert expected_id == actual_id, 'Expected gravitar ID %s, got %s' % (
            repr(expected_id), repr(actual_id))

    def test_url(self):
        email = 'Wolf@example.com'
        expected_id = 'd3514940ac1b2051c8aa42970d17e3fe'
        url = urlparse(gravatar.url(email=email))
        assert url.netloc == 'secure.gravatar.com'
        assert url.path == '/avatar/' + expected_id

    def test_defaults(self):
        email = 'Wolf@example.com'
        url = urlparse(gravatar.url(email=email, rating='x'))
        query = parse_qs(url.query)
        assert 'r' not in query
        assert query['rating'] == ['x']
