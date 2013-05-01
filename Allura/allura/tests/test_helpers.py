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

from unittest import TestCase
from os import path
from mock import Mock, patch

from pylons import tmpl_context as c
from nose.tools import eq_, assert_equals

from allura import model as M
from allura.lib import helpers as h
from allura.lib.search import inject_user
from allura.tests import decorators as td
from alluratest.controller import setup_basic_test


def setUp(self):
    """Method called by nose before running each test"""
    setup_basic_test()


class TestMakeSafePathPortion(TestCase):
    def setUp(self):
        self.f = h.make_safe_path_portion

    def test_no_latin1_chars(self):
        s = self.f(u'Задачи')
        self.assertEqual(s, '')

    def test_some_latin1_chars(self):
        s = self.f('åß∂ƒ')
        self.assertEqual(s, 'ab')

    def test_strict_mount_point_names(self):
        s = self.f('1this+is.illegal', relaxed=False)
        self.assertEqual(s, 'this-is-illegal')
        s = self.f('this-1-is-legal', relaxed=False)
        self.assertEqual(s, 'this-1-is-legal')

    def test_relaxed_mount_point_names(self):
        s = self.f('1_this+is.legal')
        self.assertEqual(s, '1_this+is.legal')
        s = self.f('not*_legal')
        self.assertEqual(s, 'not-legal')


def test_really_unicode():
    here_dir = path.dirname(__file__)
    s = h.really_unicode('\xef\xbb\xbf<?xml version="1.0" encoding="utf-8" ?>')
    assert s.startswith(u'\ufeff')
    s = h.really_unicode(open(path.join(here_dir, 'data/unicode_test.txt')).read())
    assert isinstance(s, unicode)
    # try non-ascii string in legacy 8bit encoding
    h.really_unicode(u'\u0410\u0401'.encode('cp1251'))
    # ensure invalid encodings are handled gracefully
    s = h._attempt_encodings('foo', ['LKDJFLDK'])
    assert isinstance(s, unicode)

def test_render_genshi_plaintext():
    here_dir = path.dirname(__file__)
    tpl = path.join(here_dir, 'data/genshi_hello_tmpl')
    text = h.render_genshi_plaintext(tpl, object='world')
    eq_(u'Hello, world!\n', text)

def test_find_project():
    proj, rest = h.find_project('/p/test/foo')
    assert_equals(proj.shortname, 'test')
    assert_equals(proj.neighborhood.name, 'Projects')
    proj, rest = h.find_project('/p/testable/foo')
    assert proj is None

def test_find_executable():
    assert h.find_executable('bash') == '/bin/bash'

def test_make_users():
    r = h.make_users([None]).next()
    assert r.username == '*anonymous', r

def test_make_roles():
    h.set_context('test', 'wiki', neighborhood='Projects')
    u = M.User.anonymous()
    pr = u.project_role()
    assert h.make_roles([pr._id]).next() == pr

@td.with_wiki
def test_context_setters():
    h.set_context('test', 'wiki', neighborhood='Projects')
    assert c.project is not None
    assert c.app is not None
    cfg_id = c.app.config._id
    h.set_context('test', app_config_id=cfg_id, neighborhood='Projects')
    assert c.project is not None
    assert c.app is not None
    h.set_context('test', app_config_id=str(cfg_id), neighborhood='Projects')
    assert c.project is not None
    assert c.app is not None
    c.project = c.app = None
    with h.push_context('test', 'wiki', neighborhood='Projects'):
        assert c.project is not None
        assert c.app is not None
    assert c.project == c.app == None
    with h.push_context('test', app_config_id=cfg_id, neighborhood='Projects'):
        assert c.project is not None
        assert c.app is not None
    assert c.project == c.app == None
    with h.push_context('test', app_config_id=str(cfg_id), neighborhood='Projects'):
        assert c.project is not None
        assert c.app is not None
    assert c.project == c.app == None
    del c.project
    del c.app
    with h.push_context('test', app_config_id=str(cfg_id), neighborhood='Projects'):
        assert c.project is not None
        assert c.app is not None
    assert not hasattr(c, 'project')
    assert not hasattr(c, 'app')

def test_encode_keys():
    kw = h.encode_keys({u'foo':5})
    assert type(kw.keys()[0]) != unicode

def test_ago():
    from datetime import datetime, timedelta
    import time
    assert_equals(h.ago(datetime.utcnow() - timedelta(days=2)), '2 days ago')
    assert_equals(h.ago_ts(time.time() - 60*60*2), '2 hours ago')
    d_str = (datetime.utcnow() - timedelta(hours=3)).isoformat()
    assert_equals(h.ago_string(d_str), '3 hours ago')
    assert_equals(h.ago_string('bad format'), 'unknown')
    assert_equals(h.ago_string(None), 'unknown')

def test_urlquote_unicode():
    # No exceptions please
    h.urlquote(u'\u0410')
    h.urlquoteplus(u'\u0410')

def test_sharded_path():
    assert_equals(h.sharded_path('foobar'), 'f/fo')

def test_paging_sanitizer():
    test_data = {
        # input (limit, page, total, zero-based): output (limit, page)
        (0, 0, 0): (1, 0),
        ('1', '1', 1): (1, 0),
        (5, '10', 25): (5, 4),
        ('5', 10, 25, False): (5, 5),
        (5, '-1', 25): (5, 0),
        ('5', -1, 25, False): (5, 1),
        (5, '3', 25): (5, 3),
        ('5', 3, 25, False): (5, 3)
    }
    for input, output in test_data.iteritems():
        assert (h.paging_sanitizer(*input)) == output

def test_render_any_markup_empty():
    assert_equals(h.render_any_markup('foo', ''), '<p><em>Empty File</em></p>')

def test_render_any_markup_plain():
    assert_equals(h.render_any_markup('readme.txt', '<b>blah</b>\n<script>alert(1)</script>\nfoo'),
                  '<pre>&lt;b&gt;blah&lt;/b&gt;\n&lt;script&gt;alert(1)&lt;/script&gt;\nfoo</pre>')

def test_render_any_markup_formatting():
    assert_equals(h.render_any_markup('README.md', '### foo\n'
                                      '    <script>alert(1)</script> bar'),
                  '<div class="markdown_content"><h3 id="foo">foo</h3>\n'
                  '<div class="codehilite"><pre><span class="nt">'
                  '&lt;script&gt;</span>alert(1)<span class="nt">'
                  '&lt;/script&gt;</span> bar\n</pre></div>\n</div>')


class AuditLogMock(Mock):
    logs = list()

    @classmethod
    def log(cls, message):
        cls.logs.append(message)


@patch('allura.model.AuditLog', new=AuditLogMock)
def test_log_if_changed():
    artifact = Mock()
    artifact.value = 'test'
    # change
    h.log_if_changed(artifact, 'value', 'changed', 'updated value')
    assert artifact.value == 'changed'
    assert len(AuditLogMock.logs) == 1
    assert AuditLogMock.logs[0] == 'updated value'

    # don't change
    h.log_if_changed(artifact, 'value', 'changed', 'updated value')
    assert artifact.value == 'changed'
    assert len(AuditLogMock.logs) == 1
    assert AuditLogMock.logs[0] == 'updated value'


def test_get_tool_package():
    assert h.get_tool_package('tickets') == 'forgetracker'
    assert h.get_tool_package('Wiki') == 'forgewiki'
    assert h.get_tool_package('wrong_tool') == ''


def test_get_first():
    assert_equals(h.get_first({}, 'title'), None)
    assert_equals(h.get_first({'title': None}, 'title'), None)
    assert_equals(h.get_first({'title': 'Value'}, 'title'), 'Value')
    assert_equals(h.get_first({'title': ['Value']}, 'title'), 'Value')
    assert_equals(h.get_first({'title': []}, 'title'), None)
    assert_equals(h.get_first({'title': ['Value']}, 'title'), 'Value')

@patch('allura.lib.search.c')
def test_inject_user(context):
    user = Mock(username='user01')
    assert_equals(inject_user(None, user), None)
    assert_equals(inject_user('', user), '')
    assert_equals(inject_user('query', user), 'query')
    result = inject_user('reported_by_s:$USER OR assigned_to_s:$USER', user)
    assert_equals(result, 'reported_by_s:"user01" OR assigned_to_s:"user01"')
    context.user = Mock(username='admin1')
    result = inject_user('reported_by_s:$USER OR assigned_to_s:$USER')
    assert_equals(result, 'reported_by_s:"admin1" OR assigned_to_s:"admin1"')
    context.user = Mock(username='*anonymous')
    result = inject_user('reported_by_s:$USER OR assigned_to_s:$USER')
    assert_equals(result, 'reported_by_s:"*anonymous" OR assigned_to_s:"*anonymous"')

def test_datetimeformat():
    from datetime import date
    assert h.datetimeformat(date(2013, 01, 01)) == '2013-01-01 00:00:00'
