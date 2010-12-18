from os import path, environ

from tg import config
from paste.deploy import loadapp
from paste.script.appinstall import SetupCommand
from paste.deploy import appconfig

from alluratest.controller import setup_basic_test, get_config_file
from allura.config.middleware import make_app


def setUp(self):
    """Method called by nose before running each test"""
    setup_basic_test()

def test_make_app():
    conf = appconfig('config:%s#main' % get_config_file(), relative_to=config.here)
    make_app(conf.global_conf, **conf.local_conf)
