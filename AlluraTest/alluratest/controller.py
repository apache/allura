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

import mock
import beaker.session
from formencode import variabledecode
from paste.deploy import loadapp
from paste.deploy.converters import asbool
from paste.script.appinstall import SetupCommand
from pylons import tmpl_context as c, app_globals as g
from pylons import url, request, response, session
import tg
from webtest import TestApp
from webob import Request, Response
import ew
from ming.orm import ThreadLocalORMSession
import ming.orm

from allura import model as M
import allura.lib.security
from allura.lib.app_globals import Globals
from allura.lib import helpers as h
from allura.websetup.schema import REGISTRY
#from allura.lib.custom_middleware import environ as ENV, MagicalC
from .validation import ValidatingTestApp

DFL_APP_NAME = 'main_without_authn'

# these are all helpers & base classes, and should never
# be considered test cases when imported into some test module
__test__ = False


def get_config_file(config=None):
    if not config:
        config = 'test.ini'

    try:
        conf_dir = tg.config.here
    except AttributeError:
        conf_dir = os.getcwd()
    return os.path.join(conf_dir, config)


def setup_basic_test(config=None, app_name=DFL_APP_NAME):
    '''Create clean environment for running tests'''
    try:
        conf_dir = tg.config.here
    except AttributeError:
        conf_dir = os.getcwd()
    ew.TemplateEngine.initialize({})
    test_file = os.path.join(conf_dir, get_config_file(config))
    cmd = SetupCommand('setup-app')
    cmd.run([test_file])

    # run all tasks, e.g. indexing from bootstrap operations
    while M.MonQTask.run_ready('setup'):
        ThreadLocalORMSession.flush_all()
setup_basic_test.__test__ = False  # sometimes __test__ above isn't sufficient


def setup_functional_test(config=None, app_name=DFL_APP_NAME):
    '''Create clean environment for running tests.  Also return WSGI test app'''
    config = get_config_file(config)
    setup_basic_test(config, app_name)
    conf_dir = tg.config.here
    wsgiapp = loadapp('config:%s#%s' % (config, app_name),
                      relative_to=conf_dir)
    return wsgiapp
setup_functional_test.__test__ = False  # sometimes __test__ above isn't sufficient


def setup_unit_test():
    try:
        while True:
            REGISTRY.cleanup()
    except:
        pass
    REGISTRY.prepare()
    REGISTRY.register(ew.widget_context, ew.core.WidgetContext('http', ew.ResourceManager()))
    REGISTRY.register(g, Globals())
    REGISTRY.register(c, mock.Mock())
    REGISTRY.register(url, lambda:None)
    REGISTRY.register(response, Response())
    REGISTRY.register(session, beaker.session.SessionObject({}))
    REGISTRY.register(allura.credentials, allura.lib.security.Credentials())
    c.memoize_cache = {}
    c.queued_messages = None
    c.model_cache = None
    ThreadLocalORMSession.close_all()
setup_unit_test.__test__ = False  # sometimes __test__ above isn't sufficient


def setup_global_objects():
    setup_unit_test()
    h.set_context('test', 'wiki', neighborhood='Projects')
    c.user = M.User.query.get(username='test-admin')


class TestController(object):

    application_under_test = 'main'
    validate_skip = False

    def setUp(self):
        """Method called by nose before running each test"""
        self.app = ValidatingTestApp(setup_functional_test(app_name=self.application_under_test))
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


class TestRestApiBase(TestController):

    def setUp(self):
        super(TestRestApiBase, self).setUp()
        setup_global_objects()
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
            token = M.ApiToken(user_id=user._id)
            ming.orm.session(token).flush()
            self._token_cache[username] = token

        return self._token_cache[username]

    def _api_getpost(self, method, path, api_key=None, api_timestamp=None, api_signature=None,
                 wrap_args=None, user='test-admin', status=None, **params):
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
        if api_key: params['api_key'] = api_key
        if api_timestamp: params['api_timestamp'] = api_timestamp
        if api_signature: params['api_signature'] = api_signature

        params = self.token(user).sign_request(path, params)

        fn = self.app.post if method=='POST' else self.app.get

        response = fn(
            str(path),
            params=params,
            status=status)
        if response.status_int in [301, 302]:
            return response.follow()
        else:
            return response

    def api_get(self, path, api_key=None, api_timestamp=None, api_signature=None,
                 wrap_args=None, user='test-admin', status=None, **params):
        return self._api_getpost('GET', path, api_key, api_timestamp, api_signature, wrap_args, user, status, **params)

    def api_post(self, path, api_key=None, api_timestamp=None, api_signature=None,
                 wrap_args=None, user='test-admin', status=None, **params):
        return self._api_getpost('POST', path, api_key, api_timestamp, api_signature, wrap_args, user, status, **params)
