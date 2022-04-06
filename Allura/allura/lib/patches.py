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

import re

import webob
import tg.decorators
from decorator import decorator
from tg import request
import mock
import json

from allura.lib import helpers as h
import six

_patched = False
def apply():
    global _patched
    if _patched:
        return
    _patched = True

    old_lookup_template_engine = tg.decorators.Decoration.lookup_template_engine

    @h.monkeypatch(tg.decorators.Decoration)
    def lookup_template_engine(self, request):
        '''Wrapper to handle totally borked-up HTTP-ACCEPT headers'''
        try:
            return old_lookup_template_engine(self, request)
        except Exception:
            pass
        environ = dict(request.environ, HTTP_ACCEPT='*/*')
        request = webob.Request(environ)
        return old_lookup_template_engine(self, request)

    @h.monkeypatch(tg, tg.decorators)
    def override_template(controller, template):
        '''Copy-pasted patch to allow multiple colons in a template spec'''
        if hasattr(controller, 'decoration'):
            decoration = controller.decoration
        else:
            return
        if hasattr(decoration, 'engines'):
            engines = decoration.engines
        else:
            return

        for content_type, content_engine in engines.items():
            template = template.split(':', 1)
            template.extend(content_engine[2:])
            try:
                override_mapping = request._override_mapping
            except AttributeError:
                override_mapping = request._override_mapping = {}
            override_mapping[controller.__func__] = {content_type: template}

    @h.monkeypatch(tg, tg.decorators)
    @decorator
    def without_trailing_slash(func, *args, **kwargs):
        '''Monkey-patched to use 301 redirects for SEO, and handle query strings'''
        __traceback_hide__ = 'before_and_this'  # for paste/werkzeug shorter traces
        response_type = getattr(request, 'response_type', None)
        if (request.method == 'GET' and request.path.endswith('/') and not response_type):
            location = request.path_url[:-1]
            if request.query_string:
                location += '?' + request.query_string
            raise webob.exc.HTTPMovedPermanently(location=location)
        return func(*args, **kwargs)

    @h.monkeypatch(tg, tg.decorators)
    @decorator
    def with_trailing_slash(func, *args, **kwargs):
        '''Monkey-patched to use 301 redirects for SEO, and handle query strings'''
        __traceback_hide__ = 'before_and_this'  # for paste/werkzeug shorter traces
        response_type = getattr(request, 'response_type', None)
        if (request.method == 'GET' and not request.path.endswith('/') and not response_type):
            location = request.path_url + '/'
            if request.query_string:
                location += '?' + request.query_string
            raise webob.exc.HTTPMovedPermanently(location=location)
        return func(*args, **kwargs)

    # http://blog.watchfire.com/wfblog/2011/10/json-based-xss-exploitation.html
    # change < to its unicode escape when rendering JSON out of turbogears
    # This is to avoid IE9 and earlier, which don't know the json content type
    # and may attempt to render JSON data as HTML if the URL ends in .html
    original_tg_jsonify_JSONEncoder_encode = tg.jsonify.JSONEncoder.encode

    @h.monkeypatch(tg.jsonify.JSONEncoder)
    def encode(self, o):
        return original_tg_jsonify_JSONEncoder_encode(self, o).replace('<', r'\u003C')


old_controller_call = tg.controllers.DecoratedController._call


def newrelic():
    @h.monkeypatch(tg.controllers.DecoratedController,
                   tg.controllers.decoratedcontroller.DecoratedController)
    def _call(self, controller, *args, **kwargs):
        '''Set NewRelic transaction name to actual controller name'''
        __traceback_hide__ = 'before_and_this'  # for paste/werkzeug shorter traces
        import newrelic.agent
        controller_name = newrelic.agent.callable_name(controller)
        # https://docs.newrelic.com/docs/apm/agents/python-agent/python-agent-api/settransactionname-python-agent-api/
        # if a second internal request for /error/document happens, use a lower (1) priority so original name stays
        name_priority = 1 if 'ErrorController' in controller_name else 2
        newrelic.agent.set_transaction_name(controller_name, priority=name_priority)
        return old_controller_call(self, controller, *args, **kwargs)

    import newrelic.api.error_trace
    import newrelic.api.function_trace
    # These are based on newrelic/hooks/framework_pylons.py since TG is similar to Pylons
    # capture exceptions:
    newrelic.api.error_trace.wrap_error_trace('tg.wsgiapp', 'TGApp.__call__')
    # record as its own component in transaction breakdown; should help distinguish middleware vs controller time
    newrelic.api.function_trace.wrap_function_trace('tg.controllers.tgcontroller', 'TGController.__call__')
