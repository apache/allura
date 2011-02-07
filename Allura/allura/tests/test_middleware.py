from os import path, environ
from collections import defaultdict

from tg import config
from paste.deploy import loadapp
from paste.script.appinstall import SetupCommand
from paste.deploy import appconfig
from mock import patch

from alluratest.controller import setup_basic_test, get_config_file
from allura.config.middleware import make_app
from allura.lib.custom_middleware import Environ


def setUp(self):
    """Method called by nose before running each test"""
    setup_basic_test()

def test_make_app():
    conf = appconfig('config:%s#main' % get_config_file(), relative_to=config.here)
    make_app(conf.global_conf, **conf.local_conf)

@patch('sf.phpsession.SFXSessionMgr.__new__')
@patch('sfx.middleware.configure_databases')
def test_all_middleware(__new__, configure_databases):
    conf = appconfig('config:%s#main' % get_config_file(), relative_to=config.here)
    conf.local_conf['auth.method'] = 'sfx'
    conf.local_conf['stats.sample_rate'] = '0.25'
    app = make_app(conf.global_conf, **conf.local_conf)

def test_environ():
    d = {'foo': 'qwe', 'bar': 1234}
    env = Environ()
    env.set_environment(d)
    assert env['foo'] == d['foo']
    env['baz'] = True
    assert d['baz'] == True
    del env['foo']
    assert 'foo' not in d
