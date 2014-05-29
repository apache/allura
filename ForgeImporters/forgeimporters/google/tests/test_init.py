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
from mock import patch
from formencode.validators import Invalid

from allura.tests import decorators as td
from forgeimporters.google import GoogleCodeProjectNameValidator, GoogleCodeProjectExtractor


class TestGoogleCodeProjectNameValidator(object):

    def setUp(self):
        self.readable_patcher = patch.object(GoogleCodeProjectExtractor, 'check_readable')
        self.readable_mock = self.readable_patcher.start()
        self.readable_mock.return_value = True

    def tearDown(self):
        self.readable_patcher.stop()

    def test_simple(self):
        assert_equal(
            GoogleCodeProjectNameValidator()._to_python('gmapcatcher'),
            'gmapcatcher'
        )

    def test_code_dot_google(self):
        assert_equal(
            GoogleCodeProjectNameValidator()._to_python('http://code.google.com/p/gmapcatcher/'),
            'gmapcatcher'
        )
        assert_equal(
            GoogleCodeProjectNameValidator()._to_python('https://code.google.com/p/gmapcatcher/'),
            'gmapcatcher'
        )

    def test_googlecode_com(self):
        assert_equal(
            GoogleCodeProjectNameValidator()._to_python('http://gmapcatcher.googlecode.com/'),
            'gmapcatcher'
        )
        assert_equal(
            GoogleCodeProjectNameValidator()._to_python('https://gmapcatcher.googlecode.com/'),
            'gmapcatcher'
        )

    def test_not_readable(self):
        self.readable_mock.return_value = False
        with td.raises(Invalid):
            GoogleCodeProjectNameValidator()._to_python('gmapcatcher')

    def test_invalid(self):
        with td.raises(Invalid):
            GoogleCodeProjectNameValidator()._to_python('http://code.google.com/')
        with td.raises(Invalid):
            GoogleCodeProjectNameValidator()._to_python('http://foobar.com/p/gmapcatcher')
        with td.raises(Invalid):
            GoogleCodeProjectNameValidator()._to_python('http://code.google.com/p/asdf_asdf')
        with td.raises(Invalid):
            GoogleCodeProjectNameValidator()._to_python('http://code.google.com/x/y/z')

    def test_hosted_domain(self):
        assert_equal(
            GoogleCodeProjectNameValidator()._to_python('https://code.google.com/a/eclipselabs.org/p/restclient-tool'),
            'a/eclipselabs.org/p/restclient-tool'
        )
        with td.raises(Invalid):
            GoogleCodeProjectNameValidator()._to_python('http://code.google.com/a/eclipselabs.org/bogus')
