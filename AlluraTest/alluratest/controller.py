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
import os
import urllib
import json

import mock
import beaker.session
from formencode import variabledecode
from paste.deploy import loadapp
from paste.deploy.converters import asbool
from paste.script.appinstall import SetupCommand
from pylons import tmpl_context as c, app_globals as g
from pylons import url, request, response, session
import pylons
import tg
from webob import Response, Request
import ew
from ming.orm import ThreadLocalORMSession
import ming.orm
import pkg_resources

from allura import model as M
from allura.command import CreateTroveCategoriesCommand
import allura.lib.security
from allura.lib.app_globals import Globals
from allura.lib import helpers as h
from allura.websetup.schema import REGISTRY
#from allura.lib.custom_middleware import environ as ENV, MagicalC
from .validation import ValidatingTestApp

DFL_APP_NAME = 'main'

# these are all helpers & base classes, and should never
# be considered test cases when imported into some test module
__test__ = False


def get_config_file(config=None):
    if not config:
        config = 'test.ini'

    try:
        conf_dir = tg.config.here
    except AttributeError:
        conf_dir = pkg_resources.resource_filename('allura', '..')
    return os.path.join(conf_dir, config)


def setup_config_test(config_file=None, force=False):
    '''
    This may be necessary to use within test setup that needs the app config loaded,
    especially so that the tests can be run from any directory.
    When run from the ./Allura/ dir, the setup.cfg file there causes a pylons plugin
    for nose to run, which runs `loadapp` (among other things).
    This function lets a test run from any directory.
    '''
    if not config_file:
        config_file = get_config_file()
    already_loaded = pylons.config.get('pylons.app_globals')
    if not already_loaded or force:
        loadapp('config:' + config_file)
setup_config_test.__test__ = False


def setup_basic_test(config=None, app_name=DFL_APP_NAME):
    '''
    Create clean environment for running tests.

    A lightweight alternative is setup_config_test which doesn't bootstrap app data.
    '''
    try:
        conf_dir = tg.config.here
    except AttributeError:
        conf_dir = os.getcwd()
    test_file = os.path.join(conf_dir, get_config_file(config))
    cmd = SetupCommand('setup-app')
    cmd.run([test_file])
    ew.TemplateEngine.initialize({})

    # remove unnecessary bootstrap tasks, e.g. search indexing
    M.MonQTask.query.remove({'state': 'ready'})
setup_basic_test.__test__ = False  # sometimes __test__ above isn't sufficient


def setup_functional_test(config=None, app_name=DFL_APP_NAME):
    '''Create clean environment for running tests.  Also return WSGI test app'''
    config = get_config_file(config)
    setup_basic_test(config, app_name)
    conf_dir = tg.config.here
    wsgiapp = loadapp('config:%s#%s' % (config, app_name),
                      relative_to=conf_dir)
    return wsgiapp
# sometimes __test__ above isn't sufficient
setup_functional_test.__test__ = False


def setup_unit_test():
    try:
        while True:
            REGISTRY.cleanup()
    except:
        pass
    REGISTRY.prepare()
    REGISTRY.register(ew.widget_context,
                      ew.core.WidgetContext('http', ew.ResourceManager()))
    REGISTRY.register(g, Globals())
    REGISTRY.register(c, mock.Mock())
    REGISTRY.register(url, lambda: None)
    REGISTRY.register(request, Request.blank('/'))
    REGISTRY.register(response, Response())
    REGISTRY.register(allura.credentials, allura.lib.security.Credentials())
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


class TestController(object):

    application_under_test = 'main'
    validate_skip = False

    def setUp(self):
        """Method called by nose before running each test"""
        self.app = ValidatingTestApp(
            setup_functional_test(app_name=self.application_under_test))
        self.app.extra_environ = {'REMOTE_ADDR': '127.0.0.1'}  # remote_addr needed by AntiSpam
        if self.validate_skip:
            self.app.validate_skip = self.validate_skip
        if asbool(tg.config.get('smtp.mock')):
            self.smtp_mock = mock.patch('allura.lib.mail_util.smtplib.SMTP')
            self.smtp_mock.start()

    def tearDown(self):
        """Method called by nose after running each test"""
        if asbool(tg.config.get('smtp.mock')):
            self.smtp_mock.stop()

    def webflash(self, response):
        "Extract webflash content from response."
        return urllib.unquote(response.cookies_set.get('webflash', ''))

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
        json_dict = json_dict.strip(' ;')
        return json.loads(json_dict)

    def find_form(self, resp, cond):
        """Find form on the page that meets given condition"""
        for f in resp.forms.itervalues():
            if cond(f):
                return f


class TestRestApiBase(TestController):

    def setUp(self):
        super(TestRestApiBase, self).setUp()
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
            status = [200, 201, 301, 302, 400, 403, 404]
        params = variabledecode.variable_encode(params, add_repetitions=False)

        token = self.token(user).api_key
        headers = {
            'Authorization': 'Bearer {}'.format(token)
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
