from os import path

from tg import config
from paste.deploy import loadapp
from paste.script.appinstall import SetupCommand
from paste.deploy import appconfig

from pyforge.config.middleware import make_app

def setUp(self):
    """Method called by nose before running each test"""
    # Loading the application:
    conf_dir = config.here
    wsgiapp = loadapp('config:test.ini#main',
                      relative_to=conf_dir)
    # Setting it up:
    test_file = path.join(conf_dir, 'test.ini')
    cmd = SetupCommand('setup-app')
    cmd.run([test_file])

def test_make_app():
    conf = appconfig('config:test.ini#main', relative_to=config.here)
    make_app(conf.global_conf, **conf.local_conf)
