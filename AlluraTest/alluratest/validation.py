#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

"""
Functions to syntax-validate output content
"""
from os import path
import os
import sys
import logging
import tempfile
import subprocess
import json
import six.moves.urllib.parse
import six.moves.urllib.request
import six.moves.urllib.error
import re
import pkg_resources
import six

import webtest
from webtest import TestApp
from ming.utils import LazyProperty
import requests

from allura.lib import utils

log = logging.getLogger(__name__)


class Config:

    "Config to encapsulate flexible/complex test enabled/disabled rules."
    _instance = None

    def __init__(self):
        self.ini_config = None
        pass

    @classmethod
    def instance(cls):
        if not cls._instance:
            cls._instance = cls()
        return cls._instance

    @LazyProperty
    def test_ini(self):
        if not self.ini_config:
            from . import controller
            import six.moves.configparser
            conf = six.moves.configparser.ConfigParser(
                {'validate_html5': 'false', 'validate_inlinejs': 'false'})
            conf.read(controller.get_config_file())
            self.ini_config = conf
        return self.ini_config

    def validation_enabled(self, val_type):
        env_var = os.getenv('ALLURA_VALIDATION')
        if env_var == 'all':
            return True
        elif env_var == 'none':
            return False
        elif env_var is not None:
            return val_type in env_var.split(',')

        enabled = self.test_ini.getboolean('validation', 'validate_' + val_type)
        return enabled


def report_validation_error(val_name, filename, message):
    message = f'{val_name} Validation errors ({filename}):\n{message}\n'
    raise AssertionError(message)


def dump_to_file(prefix, contents, suffix=''):
    f = tempfile.NamedTemporaryFile('w', prefix=prefix, delete=False, suffix=suffix)
    f.write(contents)
    f.close()
    return f.name


def validate_html(html_or_response):
    if hasattr(html_or_response, 'text'):
        html = html_or_response.text
    else:
        html = html_or_response

    html = html.lstrip()

    if html.startswith('<!DOCTYPE html>'):
        return validate_html5(html)
    else:
        assert False, 'Non-valid HTML: ' + html[:100] + '...'


def validate_json(json_or_response):
    if hasattr(json_or_response, 'text'):
        j = json_or_response.text
    else:
        j = json_or_response

    try:
        obj = json.loads(j)
    except Exception as e:
        raise AssertionError("Couldn't validate JSON: " + str(e) + ':' + j[:100] + '...')

    return obj


def validate_html5(html_or_response):
    if hasattr(html_or_response, 'text'):
        html = html_or_response.text
    else:
        html = html_or_response
    count = 3
    while True:
        try:
            # TODO switch to http://validator.w3.org/nu/?out=text but it has more validation errors for us to fix
            # Docs: https://github.com/validator/validator/wiki/Service-%C2%BB-Input-%C2%BB-POST-body   and other pages
            resp = requests.post('http://html5.validator.nu/nu/?out=text',  # could do out=json
                                 data=html,
                                 headers={'Content-Type': 'text/html; charset=utf-8'},
                                 timeout=5)
            resp = resp.text
            break
        except OSError:
            resp = "Couldn't connect to validation service to check the HTML"
            count -= 1
            if count == 0:
                sys.stderr.write('WARNING: ' + resp + '\n')
                break

    resp = resp.replace('“', '"').replace('”', '"').replace('–', '-')

    ignored_errors = [
        'Required attributes missing on element "object"',
        'Stray end tag "embed".',
        'Stray end tag "param".',
        r'Bad value .+? for attribute "onclick" on element "input": invalid return',
    ]
    for ignore in ignored_errors:
        resp = re.sub('Error: ' + ignore, 'Ignoring: ' + ignore, resp)

    if 'Error:' in resp:
        fname = dump_to_file('html5-', html, suffix='.html')
        message = resp.decode('ascii', 'ignore')
        report_validation_error('html5', fname, message)


def validate_html5_chunk(html):
    """ When you don't have a html & body tags - this adds it"""
    # WebTest doesn't like HTML fragments without doctype,
    # so we output them sometimes for fragments, which is hack.
    # Unhack it here.
    doctype = '<!DOCTYPE html>'
    if html.startswith(doctype):
        html = html[len(doctype):]

    html = '''<!DOCTYPE html>
    <html>
    <head><title>Not empty</title></head>
    <body>
    %s
    </body></html>''' % html
    return validate_html5(html)


def validate_js(html_or_response, within_html=False):
    if hasattr(html_or_response, 'text'):
        if html_or_response.status_int != 200:
            return
        text = html_or_response.text
    else:
        text = html_or_response
    fname = dump_to_file('eslint-', text, suffix='.html' if within_html else '.js')
    eslintrc = os.path.join(pkg_resources.get_distribution('allura').location, '../.eslintrc-es5')
    cmd = ['npm', 'run', 'eslint', '--',
           '-c', eslintrc,  # since we're in a tmp dir
           '--no-ignore',  # tmp dirs ignored by default
           ]
    if within_html:
        cmd += ['--rule', 'indent: 0']  # inline HTML always has indentation wrong
        cmd += ['--plugin', 'html']
    cmd += [fname]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stdout, stderr = p.communicate()
    if p.returncode == 0:
        os.unlink(fname)
    else:
        stdout = stdout.decode('utf8')
        report_validation_error('js', fname, stdout)


def validate_page(html_or_response):
    if Config.instance().validation_enabled('html5'):
        validate_html(html_or_response)
    if Config.instance().validation_enabled('inlinejs'):
        validate_js(html_or_response, within_html=True)


class AntiSpamTestApp(TestApp):

    def post(self, *args, **kwargs):
        antispam = utils.AntiSpam()
        if kwargs.pop('antispam', False):
            params = {
                'timestamp': antispam.timestamp_text,
                'spinner': antispam.spinner_text,
                antispam.enc('honey0'): '',
                antispam.enc('honey1'): '',
            }
            for k, v in kwargs['params'].items():
                params[antispam.enc(k)] = v
            params['_session_id'] = kwargs['params'].get('_session_id')  # exclude csrf token from encryption
            kwargs['params'] = params
        return super().post(*args, **kwargs)

    def antispam_field_names(self, form):
        """
        :param form: a WebTest form (i.e. from a self.app.get response)
        :return: a dict of field names -> antispam encoded field names
        """
        timestamp = form['timestamp'].value
        spinner = form['spinner'].value
        antispam = utils.AntiSpam(timestamp=int(timestamp), spinner=utils.AntiSpam._unwrap(spinner))
        names = list(form.fields.keys())
        name_mapping = {}
        for name in names:
            try:
                decoded = antispam.dec(name)
            except Exception:
                decoded = name
            name_mapping[decoded] = name
        return name_mapping


class PostParamCheckingTestApp(AntiSpamTestApp):

    def _validate_params(self, params, method):
        if not params:
            return
        # params can be raw data (json data post, for example)
        if isinstance(params, (bytes, (str,))):
            return
        # params can be a list or a dict
        if hasattr(params, 'items'):
            params = list(params.items())
        for k, v in params:
            if not isinstance(k, str):
                raise TypeError('%s key %s is %s, not str' %
                                (method, k, type(k)))
            self._validate_val(k, v, method)

    def _validate_val(self, k, v, method):
        if isinstance(v, (list, tuple)):
            for vv in v:
                self._validate_val(k, vv, method)
        elif not isinstance(v, (str, bytes, webtest.forms.File, webtest.forms.Upload)):
            raise TypeError(
                '%s key %s has value %s of type %s, not str. ' %
                (method, k, v, type(v)))

    def get(self, *args, **kwargs):
        params = None
        if 'params' in kwargs:
            params = kwargs['params']
        elif len(args) > 1:
            params = args[1]
        self._validate_params(params, 'get')
        return super().get(*args, **kwargs)

    def post(self, *args, **kwargs):
        params = None
        if 'params' in kwargs:
            params = kwargs['params']
        elif len(args) > 1:
            params = args[1]
        self._validate_params(params, 'post')
        return super().post(*args, **kwargs)


class ValidatingTestApp(PostParamCheckingTestApp):

    # Subclasses may set this to True to skip validation altogether
    validate_skip = False

    def _validate(self, resp, method, val_params):
        """Perform validation on webapp response. This handles responses of
        various types and forms."""
        if resp.status_int != 200:
            return

        content_type = resp.headers['Content-Type']
        if content_type.startswith('text/html'):
            if val_params['validate_chunk']:
                if Config.instance().validation_enabled('html5'):
                    validate_html5_chunk(resp.text)
            else:
                validate_page(resp)
        elif content_type.split(';', 1)[0] in ('text/plain', 'text/x-python', 'application/octet-stream'):
            pass
        elif content_type.startswith('application/json'):
            validate_json(resp.text)
        elif content_type.startswith(('application/x-javascript', 'application/javascript', 'text/javascript')):
            validate_js(resp.text)
        elif content_type.startswith('application/xml'):
            import feedparser
            d = feedparser.parse(resp.text)
            assert d.bozo == 0, 'Non-wellformed feed'
        elif content_type.startswith(('image/', 'application/x-www-form-urlencoded')):
            pass
        else:
            assert False, 'Unexpected output content type: ' + content_type

    def _get_validation_params(self, kw):
        "Separate validation params from normal TestApp methods params."
        params = {}
        for k in ('validate_skip', 'validate_chunk'):
            params[k] = kw.pop(k, False)
        return params, kw

    def get(self, *args, **kw):
        '''
        :rtype: webtest.app.TestResponse
        '''
        val_params, kw = self._get_validation_params(kw)
        resp = super().get(*args, **kw)
        if not self.validate_skip and not val_params['validate_skip']:
            self._validate(resp, 'get', val_params)
        return resp

    def post(self, *args, **kw):
        '''
        :rtype: webtest.app.TestResponse
        '''
        val_params, kw = self._get_validation_params(kw)
        resp = super().post(*args, **kw)
        if not self.validate_skip and not val_params['validate_skip']:
            self._validate(resp, 'post', val_params)
        return resp

    def delete(self, *args, **kw):
        '''
        :rtype: webtest.app.TestResponse
        '''
        val_params, kw = self._get_validation_params(kw)
        resp = super().delete(*args, **kw)
        if not self.validate_skip and not val_params['validate_skip']:
            self._validate(resp, 'delete', val_params)
        return resp
