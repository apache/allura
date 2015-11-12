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
from datetime import datetime, timedelta
import time

from mock import Mock, patch
from pylons import tmpl_context as c
from nose.tools import eq_, assert_equals
from IPython.testing.decorators import skipif, module_not_available
from datadiff import tools as dd
from webob import Request
from webob.exc import HTTPUnauthorized
from ming.orm import ThreadLocalORMSession
from jinja2 import Markup

from allura import model as M
from allura.lib import helpers as h
from allura.lib.search import inject_user
from allura.lib.security import has_access
from allura.lib.security import Credentials
from allura.tests import decorators as td
from alluratest.controller import setup_basic_test


def setUp(self):
    """Method called by nose before running each test"""
    setup_basic_test()


class TestMakeSafePathPortion(TestCase):

    def setUp(self):
        self.f = h.make_safe_path_portion

    def test_no_latin1_chars(self):
        s = self.f(u'Задачи', relaxed=False)
        self.assertEqual(s, '')

    def test_some_latin1_chars(self):
        s = self.f('åß∂ƒ', relaxed=False)
        self.assertEqual(s, 'ab')

    def test_strict_mount_point_names(self):
        s = self.f('1this+is.illegal', relaxed=False)
        self.assertEqual(s, 'this-is-illegal')
        s = self.f('this-1-is-legal', relaxed=False)
        self.assertEqual(s, 'this-1-is-legal')
        s = self.f('THIS-IS-Illegal', relaxed=False)
        self.assertEqual(s, 'this-is-illegal')

    def test_relaxed_mount_point_names(self):
        s = self.f('1_this+is.legal')
        self.assertEqual(s, '1_this+is.legal')
        s = self.f('not*_legal')
        self.assertEqual(s, 'not-legal')
        s = self.f('THIS-IS-Illegal')
        self.assertEqual(s, 'THIS-IS-Illegal')


def test_escape_json():
    inputdata = {"foo": "bar</script><img src=foobar onerror=alert(1)>"}
    outputsample = '{"foo": "bar\u003C/script>\u003Cimg src=foobar onerror=alert(1)>"}'
    outputdata = h.escape_json(inputdata)
    assert_equals(outputdata, outputsample)

def test_really_unicode():
    here_dir = path.dirname(__file__)
    s = h.really_unicode('\xef\xbb\xbf<?xml version="1.0" encoding="utf-8" ?>')
    assert s.startswith(u'\ufeff')
    s = h.really_unicode(
        open(path.join(here_dir, 'data/unicode_test.txt')).read())
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


def test_make_users():
    r = h.make_users([None]).next()
    assert r.username == '*anonymous', r


def test_make_roles():
    h.set_context('test', 'wiki', neighborhood='Projects')
    pr = M.ProjectRole.anonymous()
    assert h.make_roles([pr._id]).next() == pr


@td.with_wiki
def test_make_app_admin_only():
    h.set_context('test', 'wiki', neighborhood='Projects')
    anon = M.User.anonymous()
    dev = M.User.query.get(username='test-user')
    admin = M.User.query.get(username='test-admin')
    c.project.add_user(dev, ['Developer'])
    ThreadLocalORMSession.flush_all()
    Credentials.get().clear()
    assert has_access(c.app, 'read', user=anon)()
    assert has_access(c.app, 'read', user=dev)()
    assert has_access(c.app, 'read', user=admin)()
    assert not has_access(c.app, 'create', user=anon)()
    assert has_access(c.app, 'create', user=dev)()
    assert has_access(c.app, 'create', user=admin)()
    assert c.app.is_visible_to(anon)
    assert c.app.is_visible_to(dev)
    assert c.app.is_visible_to(admin)
    h.make_app_admin_only(c.app)
    ThreadLocalORMSession.flush_all()
    Credentials.get().clear()
    assert not has_access(c.app, 'read', user=anon)()
    assert not has_access(c.app, 'read', user=dev)()
    assert has_access(c.app, 'read', user=admin)()
    assert not has_access(c.app, 'create', user=anon)()
    assert not has_access(c.app, 'create', user=dev)()
    assert has_access(c.app, 'create', user=admin)()
    assert not c.app.is_visible_to(anon)
    assert not c.app.is_visible_to(dev)
    assert c.app.is_visible_to(admin)


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
    kw = h.encode_keys({u'foo': 5})
    assert type(kw.keys()[0]) != unicode


def test_ago():
    assert_equals(h.ago(datetime.utcnow() - timedelta(days=2)), '2 days ago')
    assert_equals(h.ago_ts(time.time() - 60 * 60 * 2), '2 hours ago')
    d_str = (datetime.utcnow() - timedelta(hours=3)).isoformat()
    assert_equals(h.ago_string(d_str), '3 hours ago')
    assert_equals(h.ago_string('bad format'), 'unknown')
    assert_equals(h.ago_string(None), 'unknown')

    monthish = datetime.utcnow() - timedelta(days=32)
    assert 'ago' not in h.ago(monthish)
    assert_equals(h.ago(monthish, show_date_after=90), '1 month ago')
    assert_equals(h.ago(monthish, show_date_after=None), '1 month ago')


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
        ('5', 3, 25, False): (5, 3),
        (9999999, 0, 0): (500, 0),
        (10, None, 0): (10, 0),
        (10, 0): (10, 0),
    }
    for input, output in test_data.iteritems():
        assert (h.paging_sanitizer(*input)) == output


def test_render_any_markup_empty():
    assert_equals(h.render_any_markup('foo', ''), '<p><em>Empty File</em></p>')


def test_render_any_markup_plain():
    assert_equals(
        h.render_any_markup(
            'readme.txt', '<b>blah</b>\n<script>alert(1)</script>\nfoo'),
        '<pre>&lt;b&gt;blah&lt;/b&gt;\n&lt;script&gt;alert(1)&lt;/script&gt;\nfoo</pre>')


def test_render_any_markup_formatting():
    assert_equals(h.render_any_markup('README.md', '### foo\n'
                                      '    <script>alert(1)</script> bar'),
                  '<div class="markdown_content"><h3 id="foo">foo</h3>\n'
                  '<div class="codehilite"><pre><span class="nt">'
                  '&lt;script&gt;</span>alert(1)<span class="nt">'
                  '&lt;/script&gt;</span> bar\n</pre></div>\n\n</div>')


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


def test_get_tool_packages():
    assert h.get_tool_packages('tickets') == ['forgetracker']
    assert h.get_tool_packages('Tickets') == ['forgetracker']
    assert h.get_tool_packages('wrong_tool') == []


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
    assert_equals(
        result, 'reported_by_s:"*anonymous" OR assigned_to_s:"*anonymous"')


def test_datetimeformat():
    from datetime import date
    assert h.datetimeformat(date(2013, 01, 01)) == '2013-01-01 00:00:00'


def test_nl2br_jinja_filter():
    assert_equals(h.nl2br_jinja_filter('foo<script>alert(1)</script>\nbar\nbaz'),
            Markup(u'foo&lt;script&gt;alert(1)&lt;/script&gt;<br>\nbar<br>\nbaz'))


def test_split_select_field_options():
    assert_equals(h.split_select_field_options('"test message" test2'),
                  ['test message', 'test2'])
    assert_equals(h.split_select_field_options('"test message test2'),
                  ['test', 'message', 'test2'])


def test_notifications_disabled():
    project = Mock(notifications_disabled=False)
    with h.notifications_disabled(project):
        assert_equals(project.notifications_disabled, True)
    assert_equals(project.notifications_disabled, False)


@skipif(module_not_available('html2text'))
def test_plain2markdown_with_html2text():
    """Test plain2markdown using html2text to escape markdown, if available."""
    text = '''paragraph

    4 spaces before this

    *blah*

here's a <tag> that should be <b>preserved</b>
Literal &gt; &Ograve; &frac14; &amp; &#38; &#x123F;
M & Ms - doesn't get escaped
http://blah.com/?x=y&a=b - not escaped either
'''

    expected = '''paragraph

4 spaces before this

\*blah\*

here's a &lt;tag&gt; that should be &lt;b&gt;preserved&lt;/b&gt;
Literal &amp;gt; &amp;Ograve; &amp;frac14; &amp;amp; &amp;\#38; &amp;\#x123F;
M & Ms - doesn't get escaped
http://blah.com/?x=y&a=b - not escaped either
'''

    dd.assert_equal(h.plain2markdown(text), expected)

    dd.assert_equal(
        h.plain2markdown('a foo  bar\n\n    code here?',
                         preserve_multiple_spaces=True),
        'a foo&nbsp; bar\n\n&nbsp;&nbsp;&nbsp; code here?')

    dd.assert_equal(
        h.plain2markdown('\ttab before (stuff)',
                         preserve_multiple_spaces=True),
        '&nbsp;&nbsp;&nbsp; tab before \(stuff\)')

    dd.assert_equal(
        h.plain2markdown('\ttab before (stuff)',
                         preserve_multiple_spaces=False),
        'tab before \(stuff\)')


@td.without_module('html2text')
def test_plain2markdown():
    """Test plain2markdown using fallback regexp to escape markdown.

    Potentially MD-special characters are aggresively escaped, as without
    knowledge of the MD parsing rules it's better to be excessive but safe.
    """
    text = '''paragraph

    4 spaces before this

    *blah*

here's a <tag> that should be <b>preserved</b>
Literal &gt; &Ograve; &frac14; &amp; &#38; &#x123F;
M & Ms - amp doesn't get escaped
http://blah.com/?x=y&a=b - not escaped either
back\\-slash escaped
'''

    expected = '''paragraph

4 spaces before this

\*blah\*

here's a &lt;tag&gt; that should be &lt;b&gt;preserved&lt;/b&gt;
Literal &amp;gt; &amp;Ograve; &amp;frac14; &amp;amp; &amp;\#38; &amp;\#x123F;
M & Ms \- amp doesn't get escaped
http://blah\.com/?x=y&a=b \- not escaped either
back\\\\\-slash escaped
'''

    dd.assert_equal(h.plain2markdown(text), expected)

    dd.assert_equal(
        h.plain2markdown('a foo  bar\n\n    code here?',
                         preserve_multiple_spaces=True),
        'a foo&nbsp; bar\n\n&nbsp;&nbsp;&nbsp; code here?')

    dd.assert_equal(
        h.plain2markdown('\ttab before (stuff)',
                         preserve_multiple_spaces=True),
        '&nbsp;&nbsp;&nbsp; tab before \(stuff\)')

    dd.assert_equal(
        h.plain2markdown('\ttab before (stuff)',
                         preserve_multiple_spaces=False),
        'tab before \(stuff\)')


class TestUrlOpen(TestCase):

    @patch('allura.lib.helpers.urllib2')
    def test_no_error(self, urllib2):
        r = h.urlopen('myurl')
        self.assertEqual(r, urllib2.urlopen.return_value)
        urllib2.urlopen.assert_called_once_with('myurl', timeout=None)

    @patch('allura.lib.helpers.urllib2.urlopen')
    def test_socket_timeout(self, urlopen):
        import socket

        def side_effect(url, timeout=None):
            raise socket.timeout()
        urlopen.side_effect = side_effect
        self.assertRaises(socket.timeout, h.urlopen, 'myurl')
        self.assertEqual(urlopen.call_count, 4)

    @patch('allura.lib.helpers.urllib2.urlopen')
    def test_socket_reset(self, urlopen):
        import socket
        import errno

        def side_effect(url, timeout=None):
            raise socket.error(errno.ECONNRESET, 'Connection reset by peer')
        urlopen.side_effect = side_effect
        self.assertRaises(socket.error, h.urlopen, 'myurl')
        self.assertEqual(urlopen.call_count, 4)

    @patch('allura.lib.helpers.urllib2.urlopen')
    def test_handled_http_error(self, urlopen):
        from urllib2 import HTTPError

        def side_effect(url, timeout=None):
            raise HTTPError('url', 408, 'timeout', None, None)
        urlopen.side_effect = side_effect
        self.assertRaises(HTTPError, h.urlopen, 'myurl')
        self.assertEqual(urlopen.call_count, 4)

    @patch('allura.lib.helpers.urllib2.urlopen')
    def test_unhandled_http_error(self, urlopen):
        from urllib2 import HTTPError

        def side_effect(url, timeout=None):
            raise HTTPError('url', 404, 'timeout', None, None)
        urlopen.side_effect = side_effect
        self.assertRaises(HTTPError, h.urlopen, 'myurl')
        self.assertEqual(urlopen.call_count, 1)


def test_absurl_no_request():
    assert_equals(h.absurl('/p/test/foobar'), 'http://localhost/p/test/foobar')


@patch.object(h, 'request',
              new=Request.blank('/p/test/foobar', base_url='https://www.mysite.com/p/test/foobar'))
def test_absurl_with_request():
    assert_equals(h.absurl('/p/test/foobar'),
                  'https://www.mysite.com/p/test/foobar')


def test_daterange():
    assert_equals(
        list(h.daterange(datetime(2013, 1, 1), datetime(2013, 1, 4))),
        [datetime(2013, 1, 1), datetime(2013, 1, 2), datetime(2013, 1, 3)])


@patch.object(h, 'request',
              new=Request.blank('/p/test/foobar', base_url='https://www.mysite.com/p/test/foobar'))
def test_login_overlay():
    with h.login_overlay():
        raise HTTPUnauthorized()
    with h.login_overlay(exceptions=['foo']):
        raise HTTPUnauthorized()
    with td.raises(HTTPUnauthorized):
        with h.login_overlay(exceptions=['foobar']):
            raise HTTPUnauthorized()


class TestIterEntryPoints(TestCase):

    def _make_ep(self, name, cls):
        m = Mock()
        m.name = name
        m.load.return_value = cls
        return m

    @patch('allura.lib.helpers.pkg_resources')
    @patch.dict(h.tg.config, {'disable_entry_points.allura': 'myapp'})
    def test_disabled(self, pkg_resources):
        pkg_resources.iter_entry_points.return_value = [
            self._make_ep('myapp', object)]
        self.assertEqual([], list(h.iter_entry_points('allura')))

    @patch('allura.lib.helpers.pkg_resources')
    def test_subclassed_ep(self, pkg_resources):
        class App(object):
            pass

        class BetterApp(App):
            pass

        pkg_resources.iter_entry_points.return_value = [
            self._make_ep('myapp', App),
            self._make_ep('myapp', BetterApp)]

        eps = list(h.iter_entry_points('allura'))
        self.assertEqual(len(eps), 1)
        self.assertEqual(BetterApp, eps[0].load())

    @patch('allura.lib.helpers.pkg_resources')
    def test_ambiguous_eps(self, pkg_resources):
        class App(object):
            pass

        class BetterApp(App):
            pass

        class BestApp(object):
            pass

        pkg_resources.iter_entry_points.return_value = [
            self._make_ep('myapp', App),
            self._make_ep('myapp', BetterApp),
            self._make_ep('myapp', BestApp)]

        self.assertRaisesRegexp(ImportError,
                                'Ambiguous \[allura\] entry points detected. '
                                'Multiple entry points with name "myapp".',
                                list, h.iter_entry_points('allura'))


def test_get_user_status():
    user = M.User.by_username('test-admin')
    assert_equals(h.get_user_status(user), 'enabled')

    user = Mock(disabled=True, pending=False)
    assert_equals(h.get_user_status(user), 'disabled')

    user = Mock(disabled=False, pending=True)
    assert_equals(h.get_user_status(user), 'pending')

    user = Mock(disabled=True, pending=True)  # not an expected combination
    assert_equals(h.get_user_status(user), 'disabled')


def test_convert_bools():
    assert_equals(h.convert_bools({'foo': 'bar', 'baz': 'false', 'abc': 0, 'def': 1, 'ghi': True}),
                  {'foo': 'bar', 'baz': False, 'abc': 0, 'def': 1, 'ghi': True})
    assert_equals(h.convert_bools({'foo': 'true', 'baz': ' TRUE '}),
                  {'foo': True, 'baz': True})
    assert_equals(h.convert_bools({'foo': 'true', 'baz': ' TRUE '}, prefix='ba'),
                  {'foo': 'true', 'baz': True})