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

from tg import tmpl_context as c
import mock
from ming.base import Object
import pytest
from formencode import validators as fev
from textwrap import dedent

from alluratest.controller import setup_unit_test
from allura import app
from allura.lib.app_globals import Icon
from allura.lib import mail_util


class TestApp:

    def setup_method(self):
        setup_unit_test()
        c.user._id = None
        c.project = mock.Mock()
        c.project.name = 'Test Project'
        c.project.shortname = 'tp'
        c.project._id = 'testproject/'
        c.project.url = lambda: '/testproject/'
        app_config = mock.Mock()
        app_config._id = None
        app_config.project_id = 'testproject/'
        app_config.tool_name = 'tool'
        app_config.options = Object(mount_point='foo')
        c.app = mock.Mock()
        c.app.config = app_config
        c.app.config.script_name = lambda: '/testproject/test_application/'
        c.app.config.url = lambda: 'http://testproject/test_application/'
        c.app.url = c.app.config.url()
        c.app.__version__ = '0.0'

    def test_config_options(self):
        options = [
            app.ConfigOption('test1', str, 'MyTestValue'),
            app.ConfigOption('test2', str, lambda:'MyTestValue')]
        assert options[0].default == 'MyTestValue'
        assert options[1].default == 'MyTestValue'

    def test_config_options_render_attrs(self):
        opt = app.ConfigOption('test1', str, None, extra_attrs={'type': 'url'})
        assert opt.render_attrs() == 'type="url"'

    def test_config_option_without_validator(self):
        opt = app.ConfigOption('test1', str, None)
        assert opt.validate(None) is None
        assert opt.validate('') == ''
        assert opt.validate('val') == 'val'

    def test_config_option_with_validator(self):
        v = fev.NotEmpty()
        opt = app.ConfigOption('test1', str, None, validator=v)
        assert opt.validate('val') == 'val'
        pytest.raises(fev.Invalid, opt.validate, None)
        pytest.raises(fev.Invalid, opt.validate, '')

    def test_options_on_install_default(self):
        a = app.Application(c.project, c.app.config)
        assert a.options_on_install() == []

    def test_options_on_install(self):
        opts = [app.ConfigOption('url', str, None),
                app.ConfigOption('private', bool, None)]
        class TestApp(app.Application):
            config_options = app.Application.config_options + opts + [
                app.ConfigOption('not_on_install', str, None),
            ]
            config_on_install = ['url', 'private']

        a = TestApp(c.project, c.app.config)
        assert a.options_on_install() == opts

    def test_main_menu(self):
        class TestApp(app.Application):
            @property
            def sitemap(self):
                children = [app.SitemapEntry('New', 'new', ui_icon=Icon('some-icon')),
                            app.SitemapEntry('Recent', 'recent'),
                            ]
                return [app.SitemapEntry('My Tool', '.')[children]]

        a = TestApp(c.project, c.app.config)
        main_menu = a.main_menu()
        assert len(main_menu) == 1
        assert main_menu[0].children == []  # default main_menu implementation should drop the children from sitemap()

    def test_sitemap(self):
        sm = app.SitemapEntry('test', '')[
            app.SitemapEntry('a', 'a/'),
            app.SitemapEntry('b', 'b/')]
        sm[app.SitemapEntry(lambda app:app.config.script_name(), 'c/')]
        bound_sm = sm.bind_app(c.app)
        assert bound_sm.url == 'http://testproject/test_application/', bound_sm.url
        assert bound_sm.children[
            -1].label == '/testproject/test_application/', bound_sm.children[-1].label
        assert len(sm.children) == 3
        sm.extend([app.SitemapEntry('a', 'a/')[
            app.SitemapEntry('d', 'd/')]])
        assert len(sm.children) == 3

    @mock.patch('allura.app.Application.PostClass.query.get')
    def test_handle_artifact_unicode(self, qg):
        """
        Tests that app.handle_artifact_message can accept utf strings
        """
        ticket = mock.MagicMock()
        ticket.get_discussion_thread.return_value = (mock.MagicMock(), mock.MagicMock())
        post = mock.MagicMock()
        qg.return_value = post

        a = app.Application(c.project, c.app.config)

        msg = dict(payload='foo ƒ†©¥˙¨ˆ'.encode(), message_id=1, headers={})
        a.handle_artifact_message(ticket, msg)
        assert post.attach.call_args[0][1].getvalue() == 'foo ƒ†©¥˙¨ˆ'.encode()

        msg = dict(payload=b'foo', message_id=1, headers={})
        a.handle_artifact_message(ticket, msg)
        assert post.attach.call_args[0][1].getvalue() == b'foo'

        msg = dict(payload="\x94my quote\x94".encode(), message_id=1, headers={})
        a.handle_artifact_message(ticket, msg)
        assert post.attach.call_args[0][1].getvalue() == '\x94my quote\x94'.encode()

        # assert against prod example
        msg_raw = dedent("""\
            Message-Id: <1502352031.3216858.1068961568.19EF48C6@webmail.messagingengine.com>
            From: foo <foo@bar.com>
            To: "[forge:site-support]" <15391@site-support.forge.p.re.sf.net>
            MIME-Version: 1.0
            Content-Transfer-Encoding: 7bit
            Content-Type: multipart/alternative; boundary="_----------=_150235203132168580"
            Date: Thu, 10 Aug 2017 10:00:31 +0200
            Subject: Re: [forge:site-support] #15391 Unable to join (my own) mailing list
            This is a multi-part message in MIME format.
            --_----------=_150235203132168580
            Content-Transfer-Encoding: quoted-printable
            Content-Type: text/plain; charset="utf-8"
            Hi
            --_----------=_150235203132168580
            Content-Transfer-Encoding: quoted-printable
            Content-Type: text/html; charset="utf-8"
            <!DOCTYPE html>
            <html><body>Hi</body></html>
            --_----------=_150235203132168580--
        """)
        msg = mail_util.parse_message(msg_raw)
        for p in [p for p in msg['parts'] if p['payload'] is not None]:
            # filter here mimics logic in `route_email`
            a.handle_artifact_message(ticket, p)
