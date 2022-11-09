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

"""Unit and functional test suite for allura."""
from __future__ import annotations

import os
import six.moves.urllib.request
import six.moves.urllib.parse
import six.moves.urllib.error
import json

import mock
import beaker.session
from formencode import variabledecode
from paste.deploy import loadapp
from paste.deploy.converters import asbool
from paste.script.appinstall import SetupCommand
from tg import tmpl_context as c, app_globals as g
from tg import url, request, response, session
import tg
from tg.wsgiapp import RequestLocals
from webob import Response, Request
import ew
from ming.orm import ThreadLocalORMSession
import ming.orm
import pkg_resources
import requests
import requests_oauthlib

from allura import model as M
from allura.command import CreateTroveCategoriesCommand
import allura.lib.security
from allura.lib.app_globals import Globals
from allura.lib import helpers as h
from allura.websetup.schema import REGISTRY
#from allura.lib.custom_middleware import environ as ENV, MagicalC
from .validation import ValidatingTestApp
import six

DFL_APP_NAME = 'main'

# these are all helpers & base classes, and should never
# be considered test cases when imported into some test module
__test__ = False


def get_config_file(config=None, current_pkg=None):
    if not config:
        config = 'test.ini'
    if not current_pkg:
        current_pkg = 'allura'

    conf_dir = pkg_resources.resource_filename(current_pkg, '..')
    conf_file = os.path.join(conf_dir, config)

    # split on "#" since it could be foo.ini#main
    if not os.path.exists(conf_file.split('#')[0]) and current_pkg != 'allura':
        # if there isn't a forgewiki/test.ini for example, then fall back to regular allura
        conf_dir = pkg_resources.resource_filename('allura', '..')
        conf_file = os.path.join(conf_dir, config)

    if not os.path.exists(conf_file.split('#')[0]):
        raise OSError(f'Cannot find .ini config file {conf_file}')
    else:
        return conf_file


def setup_basic_test(config=None, app_name=DFL_APP_NAME):
    '''
    Create clean environment for running tests, includes mongodb connection with "mim" (mongo-in-memory) and sample
    data created.

    A lightweight alternative is setup_config_test which doesn't bootstrap app data.
    '''
    try:
        conf_dir = tg.config.here
    except AttributeError:
        conf_dir = os.getcwd()
    test_file = os.path.join(conf_dir, get_config_file(config))
    """
    # setup our app, from TG quickstart example:
    from tg.util import Bunch
    from gearbox.commands.setup_app import SetupAppCommand
    cmd = SetupAppCommand(Bunch(options=Bunch(verbose_level=1)), Bunch())
    cmd.run(Bunch(config_file='config:{}'.format(test_file), section_name=None))
    """
    # setup our app without depending on gearbox (we still depend on Paste anyway)
    # uses [paste.app_install] entry point which call our setup_app()
    cmd = SetupCommand('setup-app')
    cmd.run([test_file, '--quiet'])

    ew.TemplateEngine.initialize({})

    # remove unnecessary bootstrap tasks, e.g. search indexing
    M.MonQTask.query.remove({'state': 'ready'})


setup_basic_test.__test__ = False  # sometimes __test__ above isn't sufficient


def setup_functional_test(config=None, app_name=DFL_APP_NAME, current_pkg=None):
    '''Create clean environment for running tests.  Also return WSGI test app'''
    config = get_config_file(config, current_pkg=current_pkg)
    setup_basic_test(config, app_name)
    conf_dir = tg.config.here
    wsgiapp = loadapp(f'config:{config}#{app_name}',
                      relative_to=conf_dir)
    return wsgiapp


# sometimes __test__ above isn't sufficient
setup_functional_test.__test__ = False


def setup_unit_test():
    try:
        while True:
            REGISTRY.cleanup()
    except Exception:
        pass
    REGISTRY.prepare()
    REGISTRY.register(ew.widget_context,
                      ew.core.WidgetContext('http', ew.ResourceManager()))
    REGISTRY.register(allura.credentials, allura.lib.security.Credentials())

    # turbogears has its own special magic wired up for its globals, can't use a regular Registry
    tgl = RequestLocals()
    tgl.app_globals = Globals()
    tgl.tmpl_context = mock.Mock()
    tgl.url = lambda: None
    tgl.request = Request.blank('/', remote_addr='127.0.0.1')
    tgl.response = Response()
    tg.request_local.context._push_object(tgl)

    c.model_cache = None
    ThreadLocalORMSession.close_all()


setup_unit_test.__test__ = False  # sometimes __test__ above isn't sufficient


def setup_global_objects():
    setup_unit_test()
    h.set_context('test', 'wiki', neighborhood='Projects')
    c.user = M.User.query.get(username='test-admin')


def setup_trove_categories():
    create_trove_categories = CreateTroveCategoriesCommand('create_trove_categories')
    with mock.patch.object(M.project.TroveCategoryMapperExtension, 'after_insert'),\
            mock.patch.object(M.project.TroveCategoryMapperExtension, 'after_update'),\
            mock.patch.object(M.project.TroveCategoryMapperExtension, 'after_delete'):
        create_trove_categories.run([''])


class TestController:

    application_under_test = 'main'
    validate_skip = False

    def setup_method(self, method=None):
        pkg = self.__module__.split('.')[0]
        self.app = ValidatingTestApp(
            setup_functional_test(app_name=self.application_under_test, current_pkg=pkg))
        self.app.extra_environ = {'REMOTE_ADDR': '127.0.0.1'}  # remote_addr needed by AntiSpam
        if self.validate_skip:
            self.app.validate_skip = self.validate_skip
        if asbool(tg.config.get('smtp.mock')):
            self.smtp_mock = mock.patch('allura.lib.mail_util.smtplib.SMTP')
            self.smtp_mock.start()

    def teardown_method(self, method=None):
        if asbool(tg.config.get('smtp.mock')):
            self.smtp_mock.stop()

    def webflash(self, response):
        "Extract webflash content from current state of WebTest app"
        return six.moves.urllib.parse.unquote(self.app.cookies.get('webflash', ''))

    def subscription_options(self, response):
        """
        Extract subscription options to be passed to React SubscriptionForm
        component from the <script> tag
        """
        script = None
        for s in response.html.findAll('script'):
            if s.getText().strip().startswith('document.SUBSCRIPTION_OPTIONS'):
                script = s
                break
        assert script is not None, 'subscription options not found'
        _, json_dict = script.getText().split('=')
        json_dict = json_dict.strip(' ;\n')
        return json.loads(json_dict)

    def find_form(self, resp, cond):
        """Find form on the page that meets given condition"""
        for f in resp.forms.values():
            if cond(f):
                return f


class TestRestApiBase(TestController):

    def setup_method(self, method):
        super().setup_method(method)
        self._use_token = None
        self._token_cache = {}

    def set_api_token(self, token):
        self._use_token = token

    def token(self, username):
        if self._use_token:
            return self._use_token

        # only create token once, else ming gets dupe key error
        if username not in self._token_cache:
            user = M.User.query.get(username=username)
            consumer_token = M.OAuthConsumerToken(
                name='test-%s' % str(user._id),
                description='test-app-%s' % str(user._id),
                user_id=user._id)
            request_token = M.OAuthRequestToken(
                consumer_token_id=consumer_token._id,
                user_id=user._id,
                callback='manual',
                validation_pin=h.nonce(20))
            token = M.OAuthAccessToken(
                consumer_token_id=consumer_token._id,
                request_token_id=request_token._id,
                user_id=user._id,
                is_bearer=True)
            ming.orm.session(consumer_token).flush()
            ming.orm.session(request_token).flush()
            ming.orm.session(token).flush()
            self._token_cache[username] = token

        return self._token_cache[username]

    def _api_call(self, method, path, wrap_args=None, user='test-admin', status=None, **params):
        '''
        If you need to use one of the method kwargs as a URL parameter,
        pass params={...} as a dict instead of **kwargs
        '''
        if 'params' in params:
            params = params['params']
        if wrap_args:
            params = {wrap_args: params}
        if status is None:
            status = [200, 201, 301, 302]
        if not isinstance(params, str):
            params = variabledecode.variable_encode(params, add_repetitions=False)

        token = self.token(user).api_key
        headers = {
            'Authorization': str(f'Bearer {token}')
        }

        fn = getattr(self.app, method.lower())

        response = fn(
            str(path),
            params=params,
            headers=headers,
            status=status)
        if response.status_int in [301, 302]:
            return response.follow()
        else:
            return response

    def api_get(self, path, wrap_args=None, user='test-admin', status=None, **params):
        return self._api_call('GET', path, wrap_args, user, status, **params)

    def api_post(self, path, wrap_args=None, user='test-admin', status=None, **params):
        return self._api_call('POST', path, wrap_args, user, status, **params)

    def api_delete(self, path, wrap_args=None, user='test-admin', status=None, **params):
        return self._api_call('DELETE', path, wrap_args, user, status, **params)


def oauth1_webtest(url: str, oauth_kwargs: dict, method='GET') -> tuple[str, dict, dict, dict]:
    oauth1 = requests_oauthlib.OAuth1(**oauth_kwargs)
    req = requests.Request(method, f'http://localhost{url}').prepare()
    oauth1(req)
    url, params, headers = request2webtest(req)
    extra_environ = {'username': '*anonymous'}  # we don't want to be magically logged in when hitting /rest/oauth/
    return url, params, headers, extra_environ


def request2webtest(req: requests.PreparedRequest) -> tuple[str, dict, dict]:
    url = req.url
    params = {}
    headers = {k: v.decode() for k, v in req.headers.items()}
    return url, params, headers
