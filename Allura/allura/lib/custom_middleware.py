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

import os
import re
import logging
from contextlib import contextmanager

import tg
import pkg_resources
from paste import fileapp
from paste.deploy.converters import aslist
from pylons import tmpl_context as c
from pylons.util import call_wsgi_application
from timermiddleware import Timer, TimerMiddleware
from webob import exc, Request
import pysolr

from allura.lib import helpers as h
import allura.model.repo

log = logging.getLogger(__name__)


tool_entry_points = list(h.iter_entry_points('allura'))

class StaticFilesMiddleware(object):
    '''Custom static file middleware

    Map everything in allura/public/nf/* to <script_name>/*
    For each plugin, map everything <module>/nf/<ep_name>/* to <script_name>/<ep_name>/*
    '''
    CACHE_MAX_AGE=60*60*24*365

    def __init__(self, app, script_name=''):
        self.app = app
        self.script_name = script_name
        self.directories = [
            (self.script_name + ep.name.lower() + '/', ep)
            for ep in tool_entry_points]

    def __call__(self, environ, start_response):
        environ['static.script_name'] = self.script_name
        if not environ['PATH_INFO'].startswith(self.script_name):
            return self.app(environ, start_response)
        try:
            app = self.get_app(environ)
            app.cache_control(public=True, max_age=self.CACHE_MAX_AGE)
            return app(environ, start_response)
        except OSError:
            return exc.HTTPNotFound()(environ, start_response)

    def get_app(self, environ):
        for prefix, ep in self.directories:
            if environ['PATH_INFO'].startswith(prefix):
                filename = environ['PATH_INFO'][len(prefix):]
                file_path = pkg_resources.resource_filename(
                    ep.module_name, os.path.join(
                        'nf',
                        ep.name.lower(),
                        filename))
                return fileapp.FileApp(file_path, [
                        ('Access-Control-Allow-Origin', '*')])
        filename = environ['PATH_INFO'][len(self.script_name):]
        file_path = pkg_resources.resource_filename(
            'allura', os.path.join(
                'public', 'nf',
                filename))
        return fileapp.FileApp(file_path, [
                ('Access-Control-Allow-Origin', '*')])

class LoginRedirectMiddleware(object):
    '''Actually converts a 401 into a 302 so we can do a redirect to a different
    app for login.  (StatusCodeRedirect does a WSGI-only redirect which cannot
    go to a URL not managed by the WSGI stack).'''

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        status, headers, app_iter, exc_info = call_wsgi_application(
            self.app, environ, catch_exc_info=True)
        is_api_request = environ.get('PATH_INFO', '').startswith('/rest/')
        if status[:3] == '401' and not is_api_request:
            login_url = tg.config.get('auth.login_url', '/auth/')
            if environ['REQUEST_METHOD'] == 'GET':
                return_to = environ['PATH_INFO']
                if environ.get('QUERY_STRING'):
                    return_to += '?' + environ['QUERY_STRING']
                location = tg.url(login_url, dict(return_to=return_to))
            else:
                # Don't try to re-post; the body has been lost.
                location = tg.url(login_url)
            r = exc.HTTPFound(location=location)
            return r(environ, start_response)
        start_response(status, headers, exc_info)
        return app_iter

class CSRFMiddleware(object):
    '''On POSTs, looks for a special field name that matches the value of a given
    cookie.  If this field is missing, the cookies are cleared to anonymize the
    request.'''

    def __init__(self, app, cookie_name, param_name=None):
        if param_name is None: param_name = cookie_name
        self._app = app
        self._param_name = param_name
        self._cookie_name = cookie_name

    def __call__(self, environ, start_response):
        req = Request(environ)
        cookie = req.cookies.get(self._cookie_name, None)
        if cookie is None:
            cookie = h.cryptographic_nonce()
        if req.method == 'POST':
            param = req.str_POST.pop(self._param_name, None)
            if cookie != param:
                log.warning('CSRF attempt detected, %r != %r', cookie, param)
                environ.pop('HTTP_COOKIE', None)
        def session_start_response(status, headers, exc_info = None):
            if dict(headers).get('Content-Type', '').startswith('text/html'):
                headers.append(
                    ('Set-cookie',
                     str('%s=%s; Path=/' % (self._cookie_name, cookie))))
            return start_response(status, headers, exc_info)
        return self._app(environ, session_start_response)

class SSLMiddleware(object):
    'Verify the https/http schema is correct'

    def __init__(self, app, no_redirect_pattern=None):
        self.app = app
        if no_redirect_pattern:
            self._no_redirect_re = re.compile(no_redirect_pattern)
        else:
            self._no_redirect_re = re.compile('$$$')

    def __call__(self, environ, start_response):
        req = Request(environ)
        if self._no_redirect_re.match(environ['PATH_INFO']):
            return req.get_response(self.app)(environ, start_response)
        resp = None
        try:
            request_uri = req.url
            request_uri.decode('ascii')
        except UnicodeError:
            resp = exc.HTTPNotFound()
        secure = req.environ.get('HTTP_X_SFINC_SSL', 'false') == 'true'
        srv_path = req.url.split('://', 1)[-1]
        if req.cookies.get('SFUSER'):
            if not secure:
                resp = exc.HTTPFound(location='https://' + srv_path)
        elif secure:
            resp = exc.HTTPFound(location='http://' + srv_path)

        if not resp:
            resp = self.app
        return resp(environ, start_response)

class AlluraTimerMiddleware(TimerMiddleware):
    def timers(self):
        import genshi
        import jinja2
        import markdown
        import ming
        import pymongo
        import socket
        import urllib2

        return self.entry_point_timers() + [
            Timer('jinja', jinja2.Template, 'render', 'stream', 'generate'),
            Timer('markdown', markdown.Markdown, 'convert'),
            Timer('ming', ming.odm.odmsession.ODMCursor, 'next'),  # FIXME: this may captures timings ok, but is misleading for counts
            Timer('ming', ming.odm.odmsession.ODMSession, 'flush', 'find',
                'get'),
            Timer('ming', ming.schema.Document, 'validate',
                debug_each_call=False),
            Timer('ming', ming.schema.FancySchemaItem, '_validate_required',
                '_validate_fast_missing', '_validate_optional',
                debug_each_call=False),
            Timer('mongo', pymongo.collection.Collection, 'count', 'find',
                'find_one'),
            Timer('mongo', pymongo.cursor.Cursor, 'count', 'distinct',
                '_refresh'),
            # urlopen and socket io may or may not overlap partially
            Timer('render', genshi.Stream, 'render'),
            Timer('repo.Blob.{method_name}', allura.model.repo.Blob, '*'),
            Timer('repo.Commit.{method_name}', allura.model.repo.Commit, '*'),
            Timer('repo.LastCommit.{method_name}', allura.model.repo.LastCommit, '*'),
            Timer('repo.Tree.{method_name}', allura.model.repo.Tree, '*'),
            Timer('socket_read', socket._fileobject, 'read', 'readline',
                'readlines', debug_each_call=False),
            Timer('socket_write', socket._fileobject, 'write', 'writelines',
                'flush', debug_each_call=False),
            Timer('solr', pysolr.Solr, 'add', 'delete', 'search', 'commit'),
            Timer('template', genshi.template.Template, '_prepare', '_parse',
                'generate'),
            Timer('urlopen', urllib2, 'urlopen'),
            Timer('base_repo_tool.{method_name}', allura.model.repository.RepositoryImplementation, 'last_commit_ids'),
            Timer('_diffs_copied', allura.model.repo.Commit, '_diffs_copied'),
            Timer('sequencematcher.{method_name}', allura.model.repo.SequenceMatcher, 'ratio', 'quick_ratio', 'real_quick_ratio'),
            Timer('unified_diff', allura.model.repo, 'unified_diff'),
        ] + [Timer('sidebar', ep.load(), 'sidebar_menu') for ep in tool_entry_points]

    def before_logging(self, stat_record):
        if hasattr(c, "app") and hasattr(c.app, "config"):
            stat_record.add('request_category', c.app.config.tool_name.lower())
        return stat_record

    def entry_point_timers(self):
        timers = []
        for ep in h.iter_entry_points('allura.timers'):
            func = ep.load()
            timers += aslist(func())
        return timers
