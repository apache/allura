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

"""OAuth discovery documents: RFC 8414 authorization server metadata and RFC 9728 protected resource metadata"""

from __future__ import annotations

import json

from paste.deploy.converters import asbool, aslist
from tg import config, expose, request, response
from webob import exc

from allura.controllers.auth import oauth2_scopes_supported
from allura.controllers.base import BaseController
from allura.controllers.rest import Oauth2Validator, oauth2_protected_resource, oauth2_validator

OAUTH2_REGISTRATION_PATH = '/rest/oauth2/register'


def _base_url() -> str:
    return config['base_url'].rstrip('/')


def authorization_server_metadata(validator: Oauth2Validator) -> dict:
    root = _base_url()
    public_clients = validator.dcr_enabled() or validator.cimd_enabled()
    doc = {
        'issuer': root,
        'authorization_endpoint': root + '/auth/oauth2/authorize',
        'token_endpoint': root + '/rest/oauth2/token',
        'response_types_supported': ['code'],
        'grant_types_supported': ['authorization_code', 'refresh_token'],
        'code_challenge_methods_supported': ['S256'],
        'scopes_supported': oauth2_scopes_supported(),
        # `none` is how a public client authenticates: PKCE stands in for the secret
        'token_endpoint_auth_methods_supported': ['client_secret_post', 'client_secret_basic']
                                                 + (['none'] if public_clients else []),
    }
    if not doc['scopes_supported']:
        del doc['scopes_supported']
    if validator.dcr_enabled():
        doc['registration_endpoint'] = root + OAUTH2_REGISTRATION_PATH
    if validator.cimd_enabled():
        doc['client_id_metadata_document_supported'] = True
    return doc


def protected_resource_metadata(resource: str) -> dict:
    root = _base_url()
    doc = {
        'resource': root + resource,
        'authorization_servers': [root],
        'scopes_supported': oauth2_scopes_supported(),
        'bearer_methods_supported': ['header'],
    }
    if not doc['scopes_supported']:
        del doc['scopes_supported']
    return doc


class WellKnownController(BaseController):

    @expose(content_type='application/json')
    def _default(self, document=None, *path, **kw):
        if request.method not in ('GET', 'HEAD'):
            request.environ['tg.status_code_redirect'] = True
            raise exc.HTTPMethodNotAllowed(headers=[('Allow', 'GET')])
        if not asbool(config.get('auth.oauth2.enabled', False)):
            raise exc.HTTPNotFound()
        path = [p for p in path if p]

        if document == 'oauth-authorization-server' and not path:
            doc = authorization_server_metadata(oauth2_validator())
        elif document == 'oauth-protected-resource':
            # RFC 9728 3.1: the resource's path may be appended
            resource = oauth2_protected_resource('/' + '/'.join(path)) if path else \
                next(iter(aslist(config.get('auth.oauth2.protected_resources', ''))), None)
            if not resource:
                raise exc.HTTPNotFound()
            doc = protected_resource_metadata(resource.rstrip('/'))
        else:
            raise exc.HTTPNotFound()

        # public, and fetched cross-origin by browser-based clients
        response.headers['Cache-Control'] = 'public, max-age=3600'
        response.headers.pop('Pragma', None)  # TG's default, and it contradicts the line above
        response.headers['Access-Control-Allow-Origin'] = '*'
        return json.dumps(doc, indent=2)
