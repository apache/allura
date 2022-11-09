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

import json
import time
import unittest
import datetime as dt
from os import path

import six
import ming
from ming.odm import session
from bson import ObjectId
from webob import Request
from mock import Mock, patch
from pygments import highlight
from pygments.lexers import get_lexer_for_filename
import pytest
from tg import config
import html5lib
import html5lib.treewalkers

from alluratest.controller import setup_unit_test

from allura import model as M
from allura.lib import utils
from allura.lib import helpers as h


@patch.dict('allura.lib.utils.tg.config', clear=True, foo='bar', baz='true')
class TestConfigProxy(unittest.TestCase):

    def setup_method(self, method):
        self.cp = utils.ConfigProxy(mybaz="baz")

    def test_getattr(self):
        self.assertEqual(self.cp.foo, "bar")
        self.assertEqual(self.cp.mybaz, "true")

    def test_get(self):
        self.assertEqual(self.cp.get("foo"), "bar")
        self.assertEqual(self.cp.get("mybaz"), "true")
        self.assertEqual(self.cp.get("fake"), None)
        self.assertEqual(self.cp.get("fake", "default"), "default")

    def test_get_bool(self):
        self.assertEqual(self.cp.get_bool("mybaz"), True)
        self.assertEqual(self.cp.get_bool("fake"), False)


class TestChunkedIterator(unittest.TestCase):

    def setup_method(self, method):
        setup_unit_test()
        config = {
            'ming.main.uri': 'mim://host/allura_test',
        }
        ming.configure(**config)
        for i in range(10):
            M.User.upsert('sample-user-%d' % i)

    def test_can_iterate(self):
        chunks = list(utils.chunked_find(M.User, {}, 2))
        assert len(chunks) > 1, chunks
        assert len(chunks[0]) == 2, chunks[0]

    def test_filter_on_sort_key(self):
        query = {'username':
                 {'$in': ['sample-user-1', 'sample-user-2', 'sample-user-3']}}
        chunks = list(utils.chunked_find(M.User,
                                         query,
                                         2,
                                         sort_key='username'))
        assert len(chunks) == 2, chunks
        assert len(chunks[0]) == 2, chunks[0]
        assert len(chunks[1]) == 1, chunks[1]
        assert chunks[0][0].username == 'sample-user-1'
        assert chunks[0][1].username == 'sample-user-2'
        assert chunks[1][0].username == 'sample-user-3'


class TestChunkedList(unittest.TestCase):

    def test_chunked_list(self):
        l = list(range(10))
        chunks = list(utils.chunked_list(l, 3))
        self.assertEqual(len(chunks), 4)
        self.assertEqual(len(chunks[0]), 3)
        self.assertEqual([el for sublist in chunks for el in sublist], l)


class TestAntispam(unittest.TestCase):

    def setup_method(self, method):
        setup_unit_test()
        self.a = utils.AntiSpam()

    def test_generate_fields(self):
        fields = '\n'.join(self.a.extra_fields())
        assert 'name="timestamp"' in fields, fields
        assert 'name="spinner"' in fields, fields
        assert ('class="%s"' % self.a.honey_class) in fields, fields

    def test_invalid_old(self):
        form = dict(a='1', b='2')
        r = Request.blank('/', POST=self._encrypt_form(**form))
        self.assertRaises(
            ValueError,
            utils.AntiSpam.validate_request,
            r, now=time.time() + 24 * 60 * 60 * 4 + 1)

    def test_valid_submit(self):
        form = dict(a='1', b='2')
        r = Request.blank('/', POST=self._encrypt_form(**form),
                          environ={'remote_addr': '127.0.0.1'}
                          )
        validated = utils.AntiSpam.validate_request(r)
        assert dict(a='1', b='2') == validated, validated

    def test_invalid_future(self):
        form = dict(a='1', b='2')
        r = Request.blank('/', POST=self._encrypt_form(**form))
        self.assertRaises(
            ValueError,
            utils.AntiSpam.validate_request,
            r, now=time.time() - 10)

    def test_invalid_spinner(self):
        form = dict(a='1', b='2')
        eform = self._encrypt_form(**form)
        eform['spinner'] += 'a'
        r = Request.blank('/', POST=eform)
        self.assertRaises(ValueError, utils.AntiSpam.validate_request, r)

    def test_invalid_honey(self):
        form = dict(a='1', b='2', honey0='a')
        eform = self._encrypt_form(**form)
        r = Request.blank('/', POST=eform)
        self.assertRaises(ValueError, utils.AntiSpam.validate_request, r)

    def test_missing_honey(self):
        form = dict(a='1', b='2')
        eform = self._encrypt_form(**form)
        del eform[self.a.enc('honey0')]
        r = Request.blank('/', POST=eform)
        self.assertRaises(ValueError, utils.AntiSpam.validate_request, r)

    def _encrypt_form(self, **kwargs):
        encrypted_form = {
            self.a.enc(k): v for k, v in kwargs.items()}
        encrypted_form.setdefault(self.a.enc('honey0'), '')
        encrypted_form.setdefault(self.a.enc('honey1'), '')
        encrypted_form['spinner'] = self.a.spinner_text
        encrypted_form['timestamp'] = self.a.timestamp_text
        return encrypted_form


class TestTruthyCallable(unittest.TestCase):

    def test_everything(self):
        def wrapper_func(bool_flag):
            def predicate(bool_flag=bool_flag):
                return bool_flag
            return utils.TruthyCallable(predicate)
        true_predicate = wrapper_func(True)
        false_predicate = wrapper_func(False)
        assert true_predicate(True) is True
        assert false_predicate(False) is False
        assert true_predicate() is True
        assert false_predicate() is False
        assert bool(true_predicate) is True
        assert bool(false_predicate) is False

        t, f = True, False  # use variables because '== True' would generate warnings, and we do want '==' not 'is'
        assert true_predicate == t
        assert false_predicate == f


class TestCaseInsensitiveDict(unittest.TestCase):

    def test_everything(self):
        d = utils.CaseInsensitiveDict(Foo=5)
        assert d['foo'] == d['Foo'] == d['FOO'] == 5
        d['bAr'] = 6
        assert d['bar'] == d['Bar'] == 6
        d['bar'] = 7
        assert d['bar'] == d['bAr'] == 7
        del d['bar']
        assert len(d) == 1, d
        assert d.get('foo') == 5
        d.update(foo=1, Bar=2)
        assert d.get('FOO') == 1
        assert d == dict(foo=1, bar=2)
        assert d != dict(Foo=1, bar=2)
        assert d == utils.CaseInsensitiveDict(Foo=1, bar=2)


class TestLineAnchorCodeHtmlFormatter(unittest.TestCase):

    def test_render(self):
        code = '#!/usr/bin/env python\n'\
               'print "Hello, world!"'

        formatter = utils.LineAnchorCodeHtmlFormatter(cssclass='codehilite',
                                                      linenos='inline')
        lexer = get_lexer_for_filename("some.py", encoding='chardet')
        hl_code = highlight(code, lexer, formatter)
        assert '<div class="codehilite">' in hl_code
        assert '<div id="l1" class="code_block">' in hl_code
        try:
            # older pygments
            assert '<span class="lineno">1 </span>' in hl_code
        except AssertionError:
            # newer pygments
            assert '<span class="linenos">1</span>' in hl_code


class TestIsTextFile(unittest.TestCase):

    def test_is_text_file(self):
        here_dir = path.dirname(__file__)
        text_file = path.join(here_dir, 'data/test_mime/text_file.txt')
        assert utils.is_text_file(open(text_file, 'rb').read())
        bin_file = path.join(here_dir, 'data/test_mime/bin_file')
        assert not utils.is_text_file(open(bin_file, 'rb').read())


class TestCodeStats(unittest.TestCase):

    def setup_method(self, method):
        setup_unit_test()

    def test_generate_code_stats(self):
        blob = Mock()
        blob.text = \
            """class Person(object):

    def __init__(self, name='Alice'):
        self.name = name

    def greetings(self):
        print "Hello, %s" % self.name
\t\t"""
        blob.size = len(blob.text)

        stats = utils.generate_code_stats(blob)
        assert stats['line_count'] == 8
        assert stats['data_line_count'] == 5
        assert stats['code_size'] == len(blob.text)


class TestHTMLSanitizer(unittest.TestCase):

    def walker_from_text(self, text):
        parsed = html5lib.parseFragment(text)
        TreeWalker = html5lib.treewalkers.getTreeWalker("etree")
        walker = TreeWalker(parsed)
        return walker

    def simple_tag_list(self, sanitizer):
        # no attrs, no close tag flag check, just real simple
        return [
            t['name'] for t in sanitizer if t.get('name')
        ]

    def test_html_sanitizer_iframe(self):
        walker = self.walker_from_text('<div><iframe></iframe></div>')
        p = utils.ForgeHTMLSanitizerFilter(walker)
        assert self.simple_tag_list(p) == ['div', 'div']

    def test_html_sanitizer_youtube_iframe(self):
        walker = self.walker_from_text(
            '<div><iframe src="https://www.youtube.com/embed/kOLpSPEA72U?feature=oembed"></iframe></div>')
        p = utils.ForgeHTMLSanitizerFilter(walker)
        assert self.simple_tag_list(p) == ['div', 'iframe', 'iframe', 'div']

        walker = self.walker_from_text(
            '<div><iframe src="https://www.youtube-nocookie.com/embed/kOLpSPEA72U?feature=oembed"></iframe></div>')
        p = utils.ForgeHTMLSanitizerFilter(walker)
        assert self.simple_tag_list(p) == ['div', 'iframe', 'iframe', 'div']

    def test_html_sanitizer_form_elements(self):
        walker = self.walker_from_text('<p>test</p><form method="post" action="http://localhost/foo.php"><input type=file><input type=text><textarea>asdf</textarea></form>')
        p = utils.ForgeHTMLSanitizerFilter(walker)
        assert self.simple_tag_list(p) == ['p', 'p']

    def test_html_sanitizer_checkbox(self):
        walker = self.walker_from_text('<p><input type="checkbox" disabled/><input type="text" disabled/><input type="checkbox" disabled checked/></p>')
        p = utils.ForgeHTMLSanitizerFilter(walker)
        assert self.simple_tag_list(p) == ['p', 'input', 'input', 'p']

    def test_html_sanitizer_summary(self):
        walker = self.walker_from_text('<details open="open"><summary>An Summary</summary><ul><li>Bullet Item</li></ul></details>')
        p = utils.ForgeHTMLSanitizerFilter(walker)
        assert self.simple_tag_list(p) == ['details', 'summary', 'summary', 'ul', 'li', 'li', 'ul', 'details']


def test_ip_address():
    req = Mock()
    req.remote_addr = '1.2.3.4'
    req.headers = {}
    assert (utils.ip_address(req) ==
            '1.2.3.4')


def test_ip_address_header():
    req = Mock()
    req.remote_addr = '1.2.3.4'
    req.headers = {'X_FORWARDED_FOR': '5.6.7.8'}
    with h.push_config(config, **{'ip_address_header': 'X_FORWARDED_FOR'}):
        assert (utils.ip_address(req) ==
                '5.6.7.8')


def test_ip_address_header_not_set():
    req = Mock()
    req.remote_addr = '1.2.3.4'
    req.headers = {}
    with h.push_config(config, **{'ip_address_header': 'X_FORWARDED_FOR'}):
        assert (utils.ip_address(req) ==
                '1.2.3.4')


def test_empty_cursor():
    """EmptyCursors conforms to specification of Ming's ODMCursor"""
    cursor = utils.EmptyCursor()
    assert cursor.count() == 0
    assert cursor.first() is None
    assert cursor.all() == []
    assert cursor.limit(10) == cursor
    assert cursor.skip(10) == cursor
    assert cursor.sort('name', 1) == cursor
    assert cursor.hint('index') == cursor
    assert cursor.extensions == []
    assert cursor.options(arg1='val1', arg2='val2') == cursor
    pytest.raises(ValueError, cursor.one)
    pytest.raises(StopIteration, cursor.next)
    pytest.raises(StopIteration, cursor._next_impl)


def test_DateJSONEncoder():
    data = {'message': 'Hi!',
            'date': dt.datetime(2015, 1, 30, 13, 13, 13)}
    result = json.dumps(data, cls=utils.DateJSONEncoder)
    assert result in ['{"date": "2015-01-30T13:13:13Z", "message": "Hi!"}',
                      '{"message": "Hi!", "date": "2015-01-30T13:13:13Z"}'], result


def test_clean_phone_number():
    clean = utils.clean_phone_number
    assert clean('123456789') == '123456789'
    assert clean('+123 456:789') == '123456789'
    assert clean('555-555-5555') == '5555555555'
    assert clean('1-555-555-5555') == '15555555555'


def test_phone_number_hash():
    hash = utils.phone_number_hash
    assert hash('1234567890') == hash('+123 456:7890')
    assert hash('1234567890') != hash('1234567891')


def test_skip_mod_date():
    with utils.skip_mod_date(M.Artifact):
        assert getattr(session(M.Artifact)._get(), 'skip_mod_date', None) is True
    assert getattr(session(M.Artifact)._get(), 'skip_mod_date', None) is False


class FakeAttachment:
    def __init__(self, filename):
        self._id = ObjectId()
        self.filename = filename

    def __repr__(self):
        return f'{self._id} {self.filename}'


def unique_attachments():
    ua = utils.unique_attachments
    assert [] == ua(None)
    assert [] == ua([])

    pic1 = FakeAttachment('pic.png')
    pic2 = FakeAttachment('pic.png')
    file1 = FakeAttachment('file.txt')
    file2 = FakeAttachment('file.txt')
    other = FakeAttachment('other')
    attachments = [pic1, file1, pic2, file2, pic2, other]
    expected = [file2, other, pic2]
    assert expected == ua(attachments)


def test_is_nofollow_url():
    with patch.dict(config, {'domain': 'localhost'}):
        assert not utils.is_nofollow_url('relative/path')
        assert not utils.is_nofollow_url('http://localhost/path')
        assert utils.is_nofollow_url('http://google.com/')
        assert utils.is_nofollow_url('https://google.com/')

    with patch.dict(config, {'domain': 'localhost',
                             'nofollow_exempt_domains': 'foo.com, bar.io'}):
        assert utils.is_nofollow_url('http://google.com/')
        assert utils.is_nofollow_url('http://xfoo.com/')
        assert not utils.is_nofollow_url('http://foo.com/')
        assert not utils.is_nofollow_url('http://bar.io/')
        assert utils.is_nofollow_url('http://bar.iot/')


def test_close_ipv4_addrs():
    assert utils.close_ipv4_addrs('1.2.3.4', '1.2.3.4')
    assert utils.close_ipv4_addrs('1.2.3.4', '1.2.3.255')
    assert not utils.close_ipv4_addrs('1.2.3.4', '1.2.4.4')


def test_urlencode():
    # dict - a simple one so arbitrary ordering doesn't cause problems on py2
    assert (utils.urlencode({'a': 'hello'}) ==
            'a=hello')
    # list of pairs - including unicode and bytes
    assert (utils.urlencode([('a', 1), ('b', 'ƒ'), ('c', 'ƒ'.encode())]) ==
            'a=1&b=%C6%92&c=%C6%92')
