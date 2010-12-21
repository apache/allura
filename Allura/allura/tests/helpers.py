# -*- coding: utf-8 -*- 
from os import path, environ, getcwd
import os
import sys
import logging
import tempfile
import subprocess
import json
import urllib2

import tg
import mock
import beaker.session
from paste.deploy import loadapp
from paste.script.appinstall import SetupCommand
from pylons import c, g, h, url, request, response, session
from webtest import TestApp
from webob import Request, Response
from tidylib import tidy_document
from nose.tools import ok_, assert_true, assert_false
from poster.encode import multipart_encode
from poster.streaminghttp import register_openers

import ew
from ming.orm import ThreadLocalORMSession

from allura.lib.app_globals import Globals
from allura import model as M
from allura.lib.custom_middleware import environ as ENV, MagicalC

DFL_CONFIG = 'test.ini'
DFL_APP_NAME = 'main_without_authn'
ENABLE_CONTENT_VALIDATION = False

log = logging.getLogger(__name__)


def run_app_setup():
    test_config = 'test.ini'
    conf_dir = tg.config.here = path.abspath(
        path.dirname(__file__) + '/../..')
    test_file = path.join(conf_dir, test_config)
    setup_basic_test(test_file)
    return test_config, conf_dir


def setup_basic_test(config=DFL_CONFIG, app_name=DFL_APP_NAME):
    '''Create clean environment for running tests'''
    try:
        conf_dir = tg.config.here
    except AttributeError:
        conf_dir = getcwd()
    environ = {}
    ew.TemplateEngine.initialize({})
    ew.widget_context.set_up(environ)
    ew.widget_context.resource_manager = ew.ResourceManager()
    ENV.set_environment(environ)
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

def setup_unit_test():
    from allura.lib import helpers
    g._push_object(Globals())
    c._push_object(MagicalC(mock.Mock(), ENV))
    h._push_object(helpers)
    url._push_object(lambda:None)
    c.queued_messages = None
    request._push_object(Request.blank('/'))
    response._push_object(Response())
    session._push_object(beaker.session.SessionObject({}))
    ThreadLocalORMSession.close_all()

def setup_global_objects():
    setup_unit_test()
    g.set_project('test')
    g.set_app('wiki')
    c.user = M.User.query.get(username='test-admin')
