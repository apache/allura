# -*- coding: utf-8 -*-

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

import time
import unittest
from os import path

import pylons
from webob import Request
from mock import Mock, patch
from nose.tools import assert_equal
from pygments import highlight
from pygments.lexers import get_lexer_for_filename

from alluratest.controller import setup_unit_test

from allura import model as M
from allura.lib import utils


@patch.dict('allura.lib.utils.tg.config', clear=True, foo='bar', baz='true')
class TestConfigProxy(unittest.TestCase):

    def setUp(self):
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

    def setUp(self):
        from allura import model as M
        setup_unit_test()
        for i in range(10):
            p = M.User.upsert('sample-user-%d' % i)

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
        assert_equal(chunks[0][0].username, 'sample-user-1')
        assert_equal(chunks[0][1].username, 'sample-user-2')
        assert_equal(chunks[1][0].username, 'sample-user-3')


class TestChunkedList(unittest.TestCase):

    def test_chunked_list(self):
        l = range(10)
        chunks = list(utils.chunked_list(l, 3))
        self.assertEqual(len(chunks), 4)
        self.assertEqual(len(chunks[0]), 3)
        self.assertEqual([el for sublist in chunks for el in sublist], l)


class TestAntispam(unittest.TestCase):

    def setUp(self):
        setup_unit_test()
        pylons.request._push_object(Request.blank('/'))
        pylons.request.remote_addr = '127.0.0.1'
        self.a = utils.AntiSpam()

    def test_generate_fields(self):
        fields = '\n'.join(self.a.extra_fields())
        assert 'name="timestamp"' in fields, fields
        assert 'name="spinner"' in fields, fields
        assert ('class="%s"' % self.a.honey_class) in fields, fields

    def test_valid_submit(self):
        form = dict(a='1', b='2')
        r = Request.blank('/', POST=self._encrypt_form(**form))
        validated = utils.AntiSpam.validate_request(r)
        assert dict(a='1', b='2') == validated, validated

    def test_invalid_old(self):
        form = dict(a='1', b='2')
        r = Request.blank('/', POST=self._encrypt_form(**form))
        self.assertRaises(
            ValueError,
            utils.AntiSpam.validate_request,
            r, now=time.time() + 24 * 60 * 60 + 1)

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

    def _encrypt_form(self, **kwargs):
        encrypted_form = dict(
            (self.a.enc(k), v) for k, v in kwargs.items())
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
        assert true_predicate(True) == True
        assert false_predicate(False) == False
        assert true_predicate() == True
        assert false_predicate() == False
        assert bool(true_predicate) == True
        assert bool(false_predicate) == False


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
        assert '<span class="lineno">1</span>' in hl_code


class TestIsTextFile(unittest.TestCase):

    def test_is_text_file(self):
        here_dir = path.dirname(__file__)
        assert utils.is_text_file(open(path.join(
            here_dir,
            'data/test_mime/text_file.txt')).read())
        assert not utils.is_text_file(open(path.join(
            here_dir,
            'data/test_mime/bin_file')).read())


class TestCodeStats(unittest.TestCase):

    def setUp(self):
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

    def test_html_sanitizer_iframe(self):
        p = utils.ForgeHTMLSanitizer('utf-8', '')
        p.feed('<div><iframe></iframe></div>')
        assert_equal(p.output(), '<div></div>')

    def test_html_sanitizer_youtube_iframe(self):
        p = utils.ForgeHTMLSanitizer('utf-8', '')
        p.feed(
            '<div><iframe src="http://www.youtube.com/embed/kOLpSPEA72U?feature=oembed"></iframe></div>')
        assert_equal(
            p.output(), '<div><iframe src="http://www.youtube.com/embed/kOLpSPEA72U?feature=oembed"></iframe></div>')
