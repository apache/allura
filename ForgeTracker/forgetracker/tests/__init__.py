from os import path, system, environ

from tg import config
from paste.deploy import loadapp
from paste.script.appinstall import SetupCommand
from webtest import TestApp


def run_app_setup():
    test_config = environ.get('SANDBOX') and 'sandbox-test.ini' or 'test.ini'
    conf_dir = config.here = path.abspath(
        path.dirname(__file__) + '/../..')
    test_file = path.join(conf_dir, test_config)
    cmd = SetupCommand('setup-app')
    cmd.run([test_file])
    return test_config, conf_dir


class TestController(object):
    """
    Base functional test case for the controllers.

    The pyforge application instance (``self.app``) set up in this test
    case (and descendants) has authentication disabled, so that developers can
    test the protected areas independently of the :mod:`repoze.who` plugins
    used initially. This way, authentication can be tested once and separately.

    Check pyforge.tests.functional.test_authentication for the repoze.who
    integration tests.

    This is the officially supported way to test protected areas with
    repoze.who-testutil (http://code.gustavonarea.net/repoze.who-testutil/).

    """

    application_under_test = 'main'

    def setUp(self):
        """Method called by nose before running each test"""
        test_config, conf_dir = run_app_setup()
        wsgiapp = loadapp('config:%s#%s' % (test_config, self.application_under_test),
                          relative_to=conf_dir)
        self.app = TestApp(wsgiapp)

    def tearDown(self):
        """Method called by nose after running each test"""
        pass

