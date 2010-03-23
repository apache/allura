from os import path, environ

import tg
import mock
from paste.deploy import loadapp
from paste.script.appinstall import SetupCommand
from pylons import c, g, request
from webtest import TestApp
from webob import Request

from ming.orm import ThreadLocalORMSession

from pyforge.lib.app_globals import Globals
from pyforge import model as M

DFL_CONFIG = environ.get('SANDBOX') and 'sandbox-test.ini' or 'test.ini'
DFL_APP_NAME = 'main_without_authn'

def setup_basic_test(config=DFL_CONFIG, app_name=DFL_APP_NAME):
    '''Create clean environment for running tests'''
    conf_dir = tg.config.here
    test_file = path.join(conf_dir, config)
    cmd = SetupCommand('setup-app')
    cmd.run([test_file])

def setup_functional_test(config=DFL_CONFIG, app_name=DFL_APP_NAME):
    '''Create clean environment for running tests.  Also return WSGI test app'''
    setup_basic_test(config, app_name)
    conf_dir = tg.config.here
    wsgiapp = loadapp('config:%s#%s' % (config, app_name), 
                      relative_to=conf_dir)
    return TestApp(wsgiapp)

def setup_global_objects():
    g._push_object(Globals())
    c._push_object(mock.Mock())
    request._push_object(Request.blank('/'))
    ThreadLocalORMSession.close_all()
    g.set_project('test')
    g.set_app('hello')
    c.user = M.User.query.get(username='test_admin')

