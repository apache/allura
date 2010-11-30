# -*- coding: utf-8 -*- 
from os import path, environ, getcwd
import os
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

DFL_CONFIG = environ.get('SF_SYSTEM_FUNC') and 'sandbox-test.ini' or 'test.ini'
DFL_APP_NAME = 'main_without_authn'

log = logging.getLogger(__name__)


def run_app_setup():
    test_config = environ.get('SF_SYSTEM_FUNC') and 'sandbox-test.ini' or 'test.ini'
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

#
# Functions to syntax-validate output content
#

def validate_html(html_or_response):
        if hasattr(html_or_response, 'body'):
            html = html_or_response.body
        else:
            html = html_or_response
            
        html = html.lstrip()
                    
        if html.startswith('<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"'):
            return validate_xhtml(html)
        elif html.startswith('<!DOCTYPE html">'):
            return validate_html5(html)
        else:
            assert False, 'Non-valid HTML: ' + html[:100] + '...'

def validate_xhtml(html):
        ok_warnings = ('inserting implicit <span>',
                       'replacing unexpected button by </button>',
                       'missing </button>',
                       'trimming empty <',
                       '<form> lacks "action" attribute',
                       'replacing invalid character code',
                       'discarding invalid character code',
                       '<a> proprietary attribute "alt"', # event RSS feed generated this 
                       '<table> lacks "summary" attribute',
                       
                       # parser appears to get mightily confused 
                       # see also http://sourceforge.net/tracker/?func=detail&atid=390963&aid=1986717&group_id=27659 
                       '<span> anchor "login_openid" already defined',
        )

        doc_tidied, errors = tidy_document(html)
        if errors:
            lines = html.split('\n')
            #print html 
            errors_prettified = ""
            for e in errors.split('\n'):
                if not e:
                    continue
                if '- Warning: ' in e:
                    ok = False
                    for ok_warning in ok_warnings:
                        if ok_warning in e:
                            ok = True
                            continue
                    if ok:
                        continue
                if '- Info:' in e:
                    continue
                if '- Info:' in e:
                    continue
                line_num = int(e.split(' ',2)[1])
                errors_prettified += e + "\n"
                for offset in range(-2,2+1):
                    try:
                        errors_prettified += "%s: %s\n" % (line_num+offset, lines[line_num+offset-1])
                    except IndexError as e:
                        pass
                #print lines[line_num-1] 
                errors_prettified += "\n"
            assert_false(errors_prettified, "HTML Tidy errors:\n" + errors_prettified)

def validate_xhtml_chunk(html):
        """ When you don't have a html & body tags - this adds it"""
        html = '''<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd"> 
        <html xmlns="http://www.w3.org/1999/xhtml"> 
        <head><title></title></head> 
        <body> 
        %s 
        </body></html>''' % html
        return validate_xhtml(html)

def validate_json(json_or_response):
        if hasattr(json_or_response, 'body'):
            j = json_or_response.body
        else:
            j = json_or_response

        try:
            obj = json.loads(j)
        except Exception, e:
            ok_(False, "Couldn't validate JSON: " + str(e) + ':' + j[:100] + '...')

        return obj

def validate_html5(html_or_response):
        if hasattr(html_or_response, 'body'):
            html = html_or_response.body
        else:
            html = html_or_response
        register_openers()
        params = [("out","text"),("content",html)]
        datagen, headers = multipart_encode(params)
        request = urllib2.Request("http://html5.validator.nu/", datagen, headers)
        try:
            resp = urllib2.urlopen(request, timeout=3).read()
        except:
            resp = "Couldn't connect to validation service to check the HTML"
            #ok_(False, "Couldn't connect to validation service to check the HTML") 
        
        resp = resp.replace('“','"').replace('”','"').replace('–','-')
        
        ignored_errors = [
            'Required attributes missing on element "object"',
            'Stray end tag "embed".',
            'Stray end tag "param".',
        ]
        for ignore in ignored_errors:
            resp = resp.replace('Error: ' + ignore, 'Ignoring: ' + ignore)

        if 'Error:' in resp:
            message = "Validation errors:\n" + resp
            message = message.decode('ascii','ignore')
            ok_(False, message)
        
def validate_html5_chunk(html):
        """ When you don't have a html & body tags - this adds it"""
        html = '''<!DOCTYPE html"> 
        <html> 
        <head><title></title></head> 
        <body> 
        %s 
        </body></html>''' % html
        return validate_html5(html)

def validate_js(html_or_response):
        if hasattr(html_or_response, 'body'):
            if html_or_response.status_int != 200:
                return
            html = html_or_response.body
        else:
            html = html_or_response
        basedir = path.dirname(path.abspath(__file__))
        js_dir = basedir + '/../../../tests/js'
        f = tempfile.NamedTemporaryFile(prefix='jslint', delete=False)
        f.write(html)
        f.close()
        cmd = 'java -jar ' + js_dir + '/js.jar '+ js_dir +'/jslint.js ' + f.name
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        stdout, stderr = p.communicate(html)
        if stdout.startswith('jslint: No problems found'):
            os.unlink(f.name)
            return
        stdout = stdout.decode('UTF-8', 'replace')
        raise Exception('JavaScript validation error(s) (see ' + f.name + '):  ' + '\n'.join(repr(s) for s in stdout.split('\n') if s))

def validate_page(html_or_response):
    validate_html(html_or_response)
    validate_js(html_or_response)
