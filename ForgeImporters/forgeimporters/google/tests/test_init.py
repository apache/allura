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
from BeautifulSoup import BeautifulSoup
from IPython.testing.decorators import skipif, module_not_available

from allura.tests import decorators as td
from forgeimporters.google import GoogleCodeProjectNameValidator, GoogleCodeProjectExtractor
from forgeimporters.google import _as_markdown


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


class Test_as_markdown(object):

    # this is covered by functional tests (useing test-issue.html)
    # but adding some unit tests for easier verification of hosted domain link rewriting

    def test_link_within_proj(self):
        html = BeautifulSoup('''<pre>Foo: <a href="/p/myproj/issues/detail?id=1">issue 1</a></pre>''')
        assert_equal(
            _as_markdown(html.first(), 'myproj'),
            'Foo: [issue 1](#1)'
        )

    @skipif(module_not_available('html2text'))
    def test_link_other_proj_has_html2text(self):
        html = BeautifulSoup('''<pre>Foo: <a href="/p/other-project/issues/detail?id=1">issue other-project:1</a></pre>''')
        assert_equal(
            _as_markdown(html.first(), 'myproj'),
            'Foo: [issue other-project:1](https://code.google.com/p/other-project/issues/detail?id=1)'
        )

    @td.without_module('html2text')
    def test_link_other_proj_no_html2text(self):
        # without html2text, the dash in other-project doesn't get escaped right
        html = BeautifulSoup('''<pre>Foo: <a href="/p/other-project/issues/detail?id=1">issue other-project:1</a></pre>''')
        assert_equal(
            _as_markdown(html.first(), 'myproj'),
            'Foo: [issue other\\-project:1](https://code.google.com/p/other-project/issues/detail?id=1)'
        )

    def test_link_hosted_domain_within_proj(self):
        html = BeautifulSoup('''<pre>Foo: <a href="/a/eclipselabs.org/p/myproj/issues/detail?id=1">issue 1</a></pre>''')
        assert_equal(
            _as_markdown(html.first(), 'a/eclipselabs.org/p/myproj'),
            'Foo: [issue 1](#1)'
        )

    def test_link_hosted_domain_other_proj(self):
        html = BeautifulSoup('''<pre>Foo: <a href="/a/eclipselabs.org/p/other-proj/issues/detail?id=1">issue 1</a></pre>''')
        assert_equal(
            _as_markdown(html.first(), 'a/eclipselabs.org/p/myproj'),
            'Foo: [issue 1](https://code.google.com/a/eclipselabs.org/p/other-proj/issues/detail?id=1)'
        )
