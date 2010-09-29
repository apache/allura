from os import path, environ

from tg import config
from paste.deploy import loadapp
from paste.script.appinstall import SetupCommand
from paste.deploy import appconfig

from allura.config.middleware import make_app


test_config = environ.get('SF_SYSTEM_FUNC') and 'sandbox-test.ini' or 'test.ini'

def setUp(self):
    """Method called by nose before running each test"""
    # Loading the application:
    conf_dir = config.here
    wsgiapp = loadapp('config:%s#main' % test_config,
                      relative_to=conf_dir)
    # Setting it up:
    test_file = path.join(conf_dir, test_config)
    cmd = SetupCommand('setup-app')
    cmd.run([test_file])

def test_make_app():
    conf = appconfig('config:%s#main' % test_config, relative_to=config.here)
    make_app(conf.global_conf, **conf.local_conf)
