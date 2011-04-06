"""Unit and functional test suite for allura."""
import os
import urllib

from formencode import variabledecode
import mock
import beaker.session
from paste.deploy import loadapp
from paste.script.appinstall import SetupCommand
from pylons import c, g, url, request, response, session
import tg
from webtest import TestApp
from webob import Request, Response
import ew
from ming.orm import ThreadLocalORMSession
import ming.orm

from allura import model as M
import allura.lib.security
from allura.lib.app_globals import Globals
from allura.websetup.schema import REGISTRY
#from allura.lib.custom_middleware import environ as ENV, MagicalC
from .validation import ValidatingTestApp

DFL_APP_NAME = 'main_without_authn'

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

def setup_functional_test(config=None, app_name=DFL_APP_NAME):
    '''Create clean environment for running tests.  Also return WSGI test app'''
    config = get_config_file(config)
    setup_basic_test(config, app_name)
    conf_dir = tg.config.here
    wsgiapp = loadapp('config:%s#%s' % (config, app_name),
                      relative_to=conf_dir)
    return wsgiapp

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
    REGISTRY.register(request, Request.blank('/', remote_addr='1.1.1.1'))
    REGISTRY.register(response, Response())
    REGISTRY.register(session, beaker.session.SessionObject({}))
    REGISTRY.register(allura.credentials, allura.lib.security.Credentials())
    c.queued_messages = None
    ThreadLocalORMSession.close_all()

def setup_global_objects():
    setup_unit_test()
    g.set_project('test')
    g.set_app('wiki')
    c.user = M.User.query.get(username='test-admin')


class TestController(object):

    application_under_test = 'main'
    validate_skip = False

    def setUp(self):
        """Method called by nose before running each test"""
        self.app = ValidatingTestApp(setup_functional_test(app_name=self.application_under_test))
        if self.validate_skip:
            self.app.validate_skip = self.validate_skip

    def tearDown(self):
        """Method called by nose after running each test"""
        pass

    def webflash(self, response):
        "Extract webflash content from response."
        return urllib.unquote(response.cookies_set.get('webflash', ''))


class TestRestApiBase(TestController):

    def setUp(self):
        super(TestRestApiBase, self).setUp()
        setup_global_objects()
#        h.set_context('test', 'home')
        self.user = M.User.query.get(username='test-admin')
        self.token = M.ApiToken(user_id=self.user._id)
        ming.orm.session(self.token).flush()

    def set_api_token(self, token):
        self.token = token

    def api_post(self, path, api_key=None, api_timestamp=None, api_signature=None,
                 wrap_args=None, **params):
        if wrap_args:
            params = {wrap_args: params}
        params = variabledecode.variable_encode(params, add_repetitions=False)
        if api_key: params['api_key'] = api_key
        if api_timestamp: params['api_timestamp'] = api_timestamp
        if api_signature: params['api_signature'] = api_signature
        params = self.token.sign_request(path, params)
        response = self.app.post(
            str(path),
            params=params,
            status=[200, 302, 400, 403, 404])
        if response.status_int == 302:
            return response.follow()
        else:
            return response
