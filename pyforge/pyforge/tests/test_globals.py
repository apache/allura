from os import path

import beaker.session
import webob
from tg import config
from paste.deploy import loadapp
from paste.script.appinstall import SetupCommand
from pylons import g, session, request

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
    session._push_object(beaker.session.SessionObject({}))
    request._push_object(webob.Request.blank('/test'))

def test_app_globals():
    g.oid_session()
    g.oid_session()
    g.set_project('projects/test')
    g.set_app('hello')
    assert g.app_static('css/style.css') == '/static/hello_forge/css/style.css', g.app_static('css/style.css')
    assert g.url('/foo', a='foo bar') == 'http://localhost:80/foo?a=foo+bar', g.url('/foo', a='foo bar')
    assert g.url('/foo') == 'http://localhost:80/foo', g.url('/foo')


