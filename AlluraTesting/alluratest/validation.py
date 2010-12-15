# -*- coding: utf-8 -*- 
"""
Functions to syntax-validate output content
"""
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

ENABLE_CONTENT_VALIDATION = False

log = logging.getLogger(__name__)


def validate_html(html_or_response):
        if hasattr(html_or_response, 'body'):
            html = html_or_response.body
        else:
            html = html_or_response
            
        html = html.lstrip()
                    
        if html.startswith('<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"'):
            return validate_xhtml(html)
        elif html.startswith('<!DOCTYPE html>'):
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
            f = tempfile.NamedTemporaryFile(prefix='html5-', delete=False)
            f.write(html)
            f.close()
            message = "Validation errors (" + f.name + "):\n" + resp
            message = message.decode('ascii','ignore')
            if ENABLE_CONTENT_VALIDATION:
                ok_(False, message)
            else:
                sys.stderr.write('=' * 40 + '\n' + message + '\n')
                
        
def validate_html5_chunk(html):
        """ When you don't have a html & body tags - this adds it"""
        html = '''<!DOCTYPE html> 
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
        msg = 'JavaScript validation error(s) (see ' + f.name + '):  ' + '\n'.join(repr(s) for s in stdout.split('\n') if s)
        if ENABLE_CONTENT_VALIDATION:
            raise Exception(msg)
        else:
            sys.stderr.write('=' * 40 + '\n' + msg + '\n')

def validate_page(html_or_response):
    validate_html(html_or_response)
    validate_js(html_or_response)
