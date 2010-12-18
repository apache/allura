"""Unit and functional test suite for allura."""
import os

from paste.deploy import loadapp
from paste.script.appinstall import SetupCommand
import tg
from webtest import TestApp
from webob import Request, Response
import ew

from allura.lib.custom_middleware import environ as ENV


DFL_CONFIG = os.environ.get('SF_SYSTEM_FUNC') and 'sandbox-test.ini' or 'test.ini'
DFL_APP_NAME = 'main_without_authn'

def setup_basic_test(config=DFL_CONFIG, app_name=DFL_APP_NAME):
    '''Create clean environment for running tests'''
    try:
        conf_dir = tg.config.here
    except AttributeError:
        conf_dir = os.getcwd()
    environ = {}
    ew.TemplateEngine.initialize({})
    ew.widget_context.set_up(environ)
    ew.widget_context.resource_manager = ew.ResourceManager()
    ENV.set_environment(environ)
    test_file = os.path.join(conf_dir, config)
    cmd = SetupCommand('setup-app')
    cmd.run([test_file])

def setup_functional_test(config=DFL_CONFIG, app_name=DFL_APP_NAME):
    '''Create clean environment for running tests.  Also return WSGI test app'''
    setup_basic_test(config, app_name)
    conf_dir = tg.config.here
    wsgiapp = loadapp('config:%s#%s' % (config, app_name),
                      relative_to=conf_dir)
    return TestApp(wsgiapp)


class TestController(object):
    
    application_under_test = 'main'

    def setUp(self):
        """Method called by nose before running each test"""
        self.app = setup_functional_test(app_name=self.application_under_test)
    
    def tearDown(self):
        """Method called by nose after running each test"""
        pass
