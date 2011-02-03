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

#@patch('sf.phpsession.SFXSessionMgr')
@patch('sqlalchemy.create_engine')
@patch('sfx.middleware.configure_databases')
def test_all_middleware(mk2, session_mgr):
    print session_mgr
    #, sf.phpsession.SFXSessionMgr
    from sf.phpsession import SFXSessionMgr; print SFXSessionMgr

    conf = appconfig('config:%s#main' % get_config_file(), relative_to=config.here)
    conf.local_conf['auth.method'] = 'sfx'
    conf.local_conf['stats.sample_rate'] = '0.25'
    conf.local_conf['sfx.sys_session_db_username'] = 'foo'
    conf.local_conf['sfx.sys_session_db_password'] = 'passwd'
    conf.local_conf['sfx.sys_session_db_host'] = 'localhost'
    conf.local_conf['sfx.sys_session_db_database'] = 'db'
    conf.local_conf['sfx.sys_session_db_pool_recycle'] = 1
    conf.local_conf['sfx.sys_session_db_pool_size'] = 1
    conf.local_conf['sfx.sys_session_db_pool_max_overflow'] = 1
    conf.local_conf['sfx.scheme'] = 'dontcare'
    app = make_app(conf.global_conf, **conf.local_conf)
    d = defaultdict(lambda: "str")
    d['wsgi.multiprocess'] = False
    d['paste.evalexception'] = False
    from cStringIO import StringIO
    d['wsgi.errors'] = StringIO()
    env = Environ()
    env.set_environment(d)
    app(d, lambda *a, **kw: None)

def test_environ():
    d = {'foo': 'qwe', 'bar': 1234}
    env = Environ()
    env.set_environment(d)
    assert env['foo'] == d['foo']
    env['baz'] = True
    assert d['baz'] == True
    del env['foo']
    assert 'foo' not in d
