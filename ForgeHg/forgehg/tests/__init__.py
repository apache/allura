from os import path, system, environ

from tg import config
from paste.deploy import loadapp
from paste.script.appinstall import SetupCommand
from webtest import TestApp

class TestController(object):
    """
    Base functional test case for the controllers.

    The allura application instance (``self.app``) set up in this test
    case (and descendants) has authentication disabled, so that developers can
    test the protected areas independently of the :mod:`repoze.who` plugins
    used initially. This way, authentication can be tested once and separately.

    Check allura.tests.functional.test_authentication for the repoze.who
    integration tests.

    This is the officially supported way to test protected areas with
    repoze.who-testutil (http://code.gustavonarea.net/repoze.who-testutil/).

    """

    application_under_test = 'main'
    test_config = environ.get('SF_SYSTEM_FUNC') and 'sandbox-test.ini' or 'test.ini'

    def setUp(self):
        """Method called by nose before running each test"""
        # Loading the application:
        conf_dir = config.here = path.abspath(
            path.dirname(__file__) + '/../..')
        wsgiapp = loadapp('config:%s#%s' % (self.test_config, self.application_under_test),
                          relative_to=conf_dir)
        self.app = TestApp(wsgiapp)
        # Setting it up:
        test_file = path.join(conf_dir, self.test_config)
        cmd = SetupCommand('setup-app')
        cmd.run([test_file])

    def tearDown(self):
        """Method called by nose after running each test"""
        pass
