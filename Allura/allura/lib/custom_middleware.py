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

from __future__ import unicode_literals
from __future__ import absolute_import
import os
import re
import logging

import tg
import pkg_resources
from paste import fileapp
from paste.deploy.converters import aslist
from tg import tmpl_context as c
from tg.support.middlewares import _call_wsgi_application as call_wsgi_application
from timermiddleware import Timer, TimerMiddleware
from webob import exc, Request
import pysolr
import six

from allura.lib import helpers as h
import allura.model.repository
from six.moves import range

log = logging.getLogger(__name__)


tool_entry_points = list(h.iter_entry_points('allura'))


class StaticFilesMiddleware(object):

    '''Custom static file middleware

    Map everything in allura/public/nf/* to <script_name>/*
    For each plugin, map everything <module>/nf/<ep_name>/* to <script_name>/<ep_name>/*
    '''
    CACHE_MAX_AGE = 60 * 60 * 24 * 365

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
        if '..' in environ['PATH_INFO']:
            raise OSError
        for prefix, ep in self.directories:
            if environ['PATH_INFO'].startswith(prefix):
                filename = environ['PATH_INFO'][len(prefix):]
                resource_path = os.path.join('nf', ep.name.lower(), filename)
                resource_cls = ep.load().has_resource(resource_path)
                if resource_cls:
                    file_path = pkg_resources.resource_filename(resource_cls.__module__, resource_path)
                    return fileapp.FileApp(file_path, [(str('Access-Control-Allow-Origin'), str('*'))])
        filename = environ['PATH_INFO'][len(self.script_name):]
        file_path = pkg_resources.resource_filename('allura', os.path.join('public', 'nf', filename))
        return fileapp.FileApp(file_path, [(str('Access-Control-Allow-Origin'), str('*'))])


class CORSMiddleware(object):
    '''Enables Cross-Origin Resource Sharing for REST API'''

    def __init__(self, app, allowed_methods, allowed_headers, cache=None):
        self.app = app
        self.allowed_methods = [m.upper() for m in allowed_methods]
        self.allowed_headers = set(h.lower() for h in allowed_headers)
        self.cache_preflight = cache or None

    def __call__(self, environ, start_response):
        is_api_request = environ.get('PATH_INFO', '').startswith(str('/rest/'))
        valid_cors = 'HTTP_ORIGIN' in environ
        if not is_api_request or not valid_cors:
            return self.app(environ, start_response)

        method = environ.get('REQUEST_METHOD')
        acrm = environ.get('HTTP_ACCESS_CONTROL_REQUEST_METHOD')
        if method == 'OPTIONS' and acrm:
            return self.handle_preflight_request(environ, start_response)
        else:
            return self.handle_simple_request(environ, start_response)

    def handle_simple_request(self, environ, start_response):
        def cors_start_response(status, headers, exc_info=None):
            headers.extend(self.get_response_headers(preflight=False))
            return start_response(status, headers, exc_info)
        return self.app(environ, cors_start_response)

    def handle_preflight_request(self, environ, start_response):
        method = environ.get('HTTP_ACCESS_CONTROL_REQUEST_METHOD')
        if method not in self.allowed_methods:
            return self.app(environ, start_response)
        headers = self.get_access_control_request_headers(environ)
        if not headers.issubset(self.allowed_headers):
            return self.app(environ, start_response)
        r = exc.HTTPOk(headers=self.get_response_headers(preflight=True))
        return r(environ, start_response)

    def get_response_headers(self, preflight=False):
        headers = [(str('Access-Control-Allow-Origin'), str('*'))]
        if preflight:
            ac_methods = ', '.join(self.allowed_methods)
            ac_headers = ', '.join(sorted(self.allowed_headers))
            headers.extend([
                (str('Access-Control-Allow-Methods'), str(ac_methods)),
                (str('Access-Control-Allow-Headers'), str(ac_headers)),
            ])
            if self.cache_preflight:
                headers.append(
                    (str('Access-Control-Max-Age'), str(self.cache_preflight))
                )
        return headers

    def get_access_control_request_headers(self, environ):
        headers = environ.get('HTTP_ACCESS_CONTROL_REQUEST_HEADERS', '')
        return set(h.strip().lower() for h in headers.split(',') if h.strip())


class LoginRedirectMiddleware(object):

    '''Actually converts a 401 into a 302 so we can do a redirect to a different
    app for login.  (StatusCodeRedirect does a WSGI-only redirect which cannot
    go to a URL not managed by the WSGI stack).'''

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        status, headers, app_iter, exc_info = call_wsgi_application(self.app, environ)
        is_api_request = environ.get('PATH_INFO', '').startswith(str('/rest/'))
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
        if param_name is None:
            param_name = cookie_name
        self._app = app
        self._param_name = param_name
        self._cookie_name = cookie_name

    def __call__(self, environ, start_response):
        req = Request(environ)

        # enforce POSTs
        cookie = req.cookies.get(self._cookie_name, None)
        if cookie is None:
            cookie = h.cryptographic_nonce()
        if req.method == 'POST':
            try:
                param = req.POST.pop(self._param_name, None)
            except KeyError:
                log.debug('error getting %s from POST', self._param_name, exc_info=True)
                param = None
            if cookie != param:
                log.warning('CSRF attempt detected: cookie %r != param %r', cookie, param)
                environ.pop('HTTP_COOKIE', None)  # effectively kill the existing session
                if req.path.startswith('/auth/'):
                    # for operations where you're not logged in yet (e.g. login form, pwd recovery, etc), then killing
                    # the session doesn't help, so we block the request entirely
                    resp = exc.HTTPForbidden()
                    return resp(environ, start_response)

        # Set cookie for use in later forms:

        # in addition to setting a cookie, set this so its available on first response before cookie gets created in browser
        environ[self._cookie_name] = cookie

        def session_start_response(status, headers, exc_info=None):
            if dict(headers).get('Content-Type', '').startswith('text/html'):
                headers.append(
                    (str('Set-cookie'),
                     str('%s=%s; Path=/' % (self._cookie_name, cookie))))
            return start_response(status, headers, exc_info)

        return self._app(environ, session_start_response)


class SSLMiddleware(object):

    'Verify the https/http schema is correct'

    def __init__(self, app, no_redirect_pattern=None, force_ssl_pattern=None, force_ssl_logged_in=False):
        self.app = app
        if no_redirect_pattern:
            self._no_redirect_re = re.compile(no_redirect_pattern)
        else:
            self._no_redirect_re = re.compile('$$$')
        if force_ssl_pattern:
            self._force_ssl_re = re.compile(force_ssl_pattern)
        else:
            self._force_ssl_re = re.compile('$$$')
        self._force_ssl_logged_in = force_ssl_logged_in

    def __call__(self, environ, start_response):
        req = Request(environ)
        if self._no_redirect_re.match(environ['PATH_INFO']):
            return req.get_response(self.app)(environ, start_response)
        resp = None

        try:
            request_uri = req.url
            six.ensure_binary(request_uri).decode('ascii')
        except UnicodeError:
            resp = exc.HTTPBadRequest()
        else:
            secure = req.url.startswith('https://')
            srv_path = req.url.split('://', 1)[-1]
            # allura-loggedin is a non-secure cookie as a flag to know that the user has a session over on https
            force_ssl = (self._force_ssl_logged_in and req.cookies.get('allura-loggedin')) \
                        or self._force_ssl_re.match(environ['PATH_INFO'])
            if req.environ.get('tg.original_request'):
                # if an error occurs, then /error/document is fetched (denoted by tg.original_request)
                # and we don't want to do any redirects within that sub-request
                pass
            elif not secure and force_ssl:
                resp = exc.HTTPFound(location='https://' + srv_path)
            elif secure and not force_ssl:
                resp = exc.HTTPFound(location='http://' + srv_path)
            if not resp:
                resp = self.app
        return resp(environ, start_response)


class SetRequestHostFromConfig(object):
    """
    Set request properties for host and port, based on the 'base_url' config setting.
    This permits code to use request.host etc to construct URLs correctly, even when behind a proxy, like in docker
    """
    def __init__(self, app, config):
        self.app = app
        self.config = config

    def __call__(self, environ, start_response):
        environ['HTTP_HOST'] = tg.config['base_url'].split('://')[1]
        # setting environ['wsgi.url_scheme'] would make some links use the right http/https scheme, but is not safe
        # since the app may accept both http and https inbound requests, and many places in code need to check that
        # potentially could set wsgi.url_scheme based on 'HTTP_X_FORWARDED_SSL' == 'on' and/or
        #   'HTTP_X_FORWARDED_PROTO' == 'https'
        req = Request(environ)
        try:
            req.params  # check for malformed unicode, this is the first middleware that might trip over it.
            resp = self.app
        except UnicodeError:
            resp = exc.HTTPBadRequest()


        return resp(environ, start_response)


class AlluraTimerMiddleware(TimerMiddleware):

    def timers(self):
        import jinja2
        import markdown
        import ming
        import pymongo
        import socket
        if six.PY2:
            import urllib2 as urlopen_pkg
        else:
            import urllib.requests as urlopen_pkg
        import activitystream
        import pygments
        import difflib

        timers = self.entry_point_timers() + [
            Timer(
                'activitystream.director.{method_name}', allura.model.timeline.Director,
                'create_activity', 'create_timeline', 'get_timeline'),
            Timer('activitystream.aggregator.{method_name}',
                  allura.model.timeline.Aggregator, '*'),
            Timer('activitystream.node_manager.{method_name}',
                  activitystream.managers.NodeManager, '*'),
            Timer('activitystream.activity_manager.{method_name}',
                  activitystream.managers.ActivityManager, '*'),
            Timer('jinja', jinja2.Template, 'render', 'stream', 'generate'),
            Timer('markdown', markdown.Markdown, 'convert'),
            Timer('ming', ming.odm.odmsession.ODMCursor, 'next',  # FIXME: this may captures timings ok, but is misleading for counts
                  debug_each_call=False),
            Timer('ming', ming.odm.odmsession.ODMSession,
                  'insert_now', 'update_now', 'delete_now',
                  'find', 'find_and_modify', 'remove', 'update', 'update_if_not_modified',
                  'aggregate', 'group', 'map_reduce', 'inline_map_reduce', 'distinct',
                  ),
            Timer('ming', ming.schema.Document, 'validate',
                  debug_each_call=False),
            Timer('ming', ming.schema.FancySchemaItem, '_validate_required',
                  '_validate_fast_missing', '_validate_optional',
                  debug_each_call=False),
            Timer('mongo', pymongo.collection.Collection, 'count', 'find',
                  'find_one', 'aggregate', 'group', 'map_reduce',
                  'inline_map_reduce', 'find_and_modify',
                  'insert', 'save', 'update', 'remove', 'drop'),
            Timer('mongo', pymongo.cursor.Cursor, 'count', 'distinct',
                  '_refresh'),
            # urlopen and socket io may or may not overlap partially
            Timer('repo.Blob.{method_name}', allura.model.repository.Blob, '*'),
            Timer('repo.Commit.{method_name}', allura.model.repository.Commit, '*'),
            Timer('repo.LastCommit.{method_name}',
                  allura.model.repository.LastCommit, '*'),
            Timer('repo.Tree.{method_name}', allura.model.repository.Tree, '*'),
            Timer('socket_read', socket._fileobject, 'read', 'readline',
                  'readlines', debug_each_call=False),
            Timer('socket_write', socket._fileobject, 'write', 'writelines',
                  'flush', debug_each_call=False),
            Timer('solr', pysolr.Solr, 'add', 'delete', 'search', 'commit'),
            Timer('urlopen', urlopen_pkg, 'urlopen'),
            Timer('base_repo_tool.{method_name}',
                  allura.model.repository.RepositoryImplementation, 'last_commit_ids'),
            Timer('pygments', pygments, 'highlight'),  # often called from within a template so will overlap w/ jinja
            Timer('difflib', difflib, '_mdiff', 'unified_diff'),
        ] + [Timer('sidebar', ep.load(), 'sidebar_menu') for ep in tool_entry_points]

        try:
            import ldap
        except ImportError:
            pass
        else:
            timers += [
                Timer('ldap', ldap, 'initialize'),
                Timer('ldap', ldap.ldapobject.LDAPObject,
                      'bind_s', 'unbind_s', 'add_s', 'modify_s', 'search_s'),
            ]

        return timers

    def before_logging(self, stat_record):
        if hasattr(c, "app") and hasattr(c.app, "config"):
            stat_record.add('request_category', c.app.config.tool_name.lower())
        return stat_record

    @classmethod
    def entry_point_timers(cls, module_prefix=None):
        timers = []
        for ep in h.iter_entry_points('allura.timers'):
            if not module_prefix or ep.module_name.startswith(module_prefix):
                func = ep.load()
                timers += aslist(func())
        return timers


class RememberLoginMiddleware(object):
    '''
    This middleware changes session's cookie expiration time according to login_expires
    session variable'''

    def __init__(self, app, config):
        self.app = app
        self.config = config

    def __call__(self, environ, start_response):

        def remember_login_start_response(status, headers, exc_info=None):
            session = environ['beaker.session']
            username = session.get('username')
            login_expires = session.get('login_expires')
            if username and login_expires is not None:
                if login_expires is True:
                    # no specific expiration, lasts for duration of "browser session"
                    session.cookie[session.key]['expires'] = ''
                else:
                    # set it to the given date
                    session._set_cookie_expires(login_expires)
                # Replace the cookie header that SessionMiddleware set
                # with one that has the new expires parameter value
                cookie = session.cookie[session.key].output(header=str(''))
                for i in range(len(headers)):
                    header, contents = headers[i]
                    if header == 'Set-cookie' and \
                            contents.lstrip().startswith(session.key):
                        headers[i] = (str('Set-cookie'), cookie)
                        break
            return start_response(status, headers, exc_info)

        return self.app(environ, remember_login_start_response)
