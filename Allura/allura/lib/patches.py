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

import webob
import tg.decorators
from decorator import decorator
from pylons import request

from allura.lib import helpers as h

def apply():
    old_lookup_template_engine = tg.decorators.Decoration.lookup_template_engine

    @h.monkeypatch(tg.decorators.Decoration)
    def lookup_template_engine(self, request):
        '''Wrapper to handle totally borked-up HTTP-ACCEPT headers'''
        try:
            return old_lookup_template_engine(self, request)
        except:
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

        for content_type, content_engine in engines.iteritems():
            template = template.split(':', 1)
            template.extend(content_engine[2:])
            try:
                override_mapping = request._override_mapping
            except AttributeError:
                override_mapping = request._override_mapping = {}
            override_mapping[controller.im_func] = {content_type: template}

    @h.monkeypatch(tg, tg.decorators)
    @decorator
    def without_trailing_slash(func, *args, **kwargs):
        '''Monkey-patched to use 301 redirects for SEO'''
        response_type = getattr(request, 'response_type', None)
        if (request.method == 'GET' and request.path.endswith('/')
                and not response_type and len(request.params)==0):
            raise webob.exc.HTTPMovedPermanently(location=request.url[:-1])
        return func(*args, **kwargs)

    @h.monkeypatch(tg, tg.decorators)
    @decorator
    def with_trailing_slash(func, *args, **kwargs):
        '''Monkey-patched to use 301 redirects for SEO'''
        response_type = getattr(request, 'response_type', None)
        if (request.method == 'GET' and not(request.path.endswith('/'))
                and not response_type and len(request.params)==0):
            raise webob.exc.HTTPMovedPermanently(location=request.url+'/')
        return func(*args, **kwargs)


def newrelic():
    old_call = tg.controllers.DecoratedController._call

    @h.monkeypatch(tg.controllers.DecoratedController,
                   tg.controllers.decoratedcontroller.DecoratedController)
    def _call(self, controller, *args, **kwargs):
        '''Set NewRelic transaction name to actual controller name'''
        import newrelic.agent
        newrelic.agent.set_transaction_name(newrelic.agent.callable_name(controller))
        return old_call(self, controller, *args, **kwargs)
