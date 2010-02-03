from os import path, system

from tg import config
from forgescm.tests import test_helper

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
    
    def setUp(self):
        self.app = test_helper.test_setup_app()
    
    def tearDown(self):
        """Method called by nose after running each test"""
        pass
