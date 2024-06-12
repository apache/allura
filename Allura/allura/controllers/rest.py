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

"""REST Controller"""
from __future__ import annotations
import json
import logging
from datetime import datetime, timedelta
from urllib.parse import unquote, urlparse, parse_qs, parse_qsl

import oauthlib.oauth1
import oauthlib.oauth2
import oauthlib.common
from paste.util.converters import asbool
from webob import exc
import tg
from tg import expose, flash, redirect, config
from tg import tmpl_context as c, app_globals as g
from tg import request, response
from tg.decorators import without_trailing_slash
import colander
from ming.odm import session

from allura import model as M
from allura.controllers.auth import AuthRestController
from allura.lib import helpers as h
from allura.lib import security
from allura.lib import plugin
from allura.lib.exceptions import Invalid, ForgeError
from allura.lib.decorators import require_post
from allura.lib.project_create_helpers import make_newproject_schema, deserialize_project, create_project_with_attrs
from allura.lib.security import has_access
import six


log = logging.getLogger(__name__)


class RestController:

    def __init__(self):
        self.oauth = OAuthNegotiator()
        self.auth = AuthRestController()

        if self._is_oauth2_enabled():
            self.oauth2 = Oauth2Negotiator()

    def _is_oauth2_enabled(self):
        return asbool(config.get('auth.oauth2.enabled', False))

    def _check_security(self):
        if not request.path.startswith(('/rest/oauth/', '/rest/oauth2/')):  # everything but OAuthNegotiators
            c.api_token = self._authenticate_request()
            if c.api_token:
                c.user = c.api_token.user

    def _authenticate_request(self):
        'Based on request.params or oauth, authenticate the request'
        headers_auth = 'Authorization' in request.headers
        params_auth = 'oauth_token' in request.params
        params_auth = params_auth or 'access_token' in request.params
        if headers_auth or params_auth:
            try:
                access_token = self.oauth._authenticate()
            except exc.HTTPUnauthorized:
                if not self._is_oauth2_enabled():
                    raise

                if params_auth:
                    raise exc.HTTPUnauthorized('Do not use tokens in URL, instead use header Authorization: Bearer $TOKEN')

                access_token = self.oauth2._authenticate()
                if not access_token:
                    raise

            return access_token
        else:
            return None

    @expose('json:')
    def index(self, **kw):
        """Return site summary information as JSON.

        Currently, the only summary information returned are any site_stats
        whose providers are defined as entry points under the
        'allura.site_stats' group in a package or tool's setup.py, e.g.::

            [allura.site_stats]
            new_users_24hr = allura.site_stats:new_users_24hr

        The stat provider will be called with no arguments to generate the
        stat, which will be included under a key equal to the name of the
        entry point.

        Example output::

            {
                'site_stats': {
                    'new_users_24hr': 10
                }
            }
        """
        summary = dict()
        stats = dict()
        for stat, provider in g.entry_points['site_stats'].items():
            stats[stat] = provider()
        if stats:
            summary['site_stats'] = stats
        return summary

    @expose('json:')
    def notification(self, cookie='', url='', tool_name='', **kw):
        r = g.theme._get_site_notification(
            url=url,
            user=c.user,
            tool_name=tool_name,
            site_notification_cookie_value=cookie
        )
        if r:
            return dict(notification=r[0], cookie=r[1])
        return {}

    @expose()
    def _lookup(self, name, *remainder):
        neighborhood = M.Neighborhood.query.get(url_prefix='/' + name + '/')
        if not neighborhood:
            raise exc.HTTPNotFound(name)
        return NeighborhoodRestController(neighborhood), remainder


class Oauth1Validator(oauthlib.oauth1.RequestValidator):

    def validate_client_key(self, client_key: str, request: oauthlib.common.Request) -> bool:
        return M.OAuthConsumerToken.query.get(api_key=client_key) is not None

    def get_client_secret(self, client_key, request):
        return M.OAuthConsumerToken.query.get(api_key=client_key).secret_key  # NoneType error? you need dummy_oauths()

    def save_request_token(self, token: dict, request: oauthlib.common.Request) -> None:
        consumer_token = M.OAuthConsumerToken.query.get(api_key=request.client_key)
        req_token = M.OAuthRequestToken(
            api_key=token['oauth_token'],
            secret_key=token['oauth_token_secret'],
            consumer_token_id=consumer_token._id,
            callback=request.oauth_params.get('oauth_callback', 'oob'),
        )
        session(req_token).flush()
        log.info('Saving new request token with key: %s', req_token.api_key)

    def verify_request_token(self, token: str, request: oauthlib.common.Request) -> bool:
        return M.OAuthRequestToken.query.get(api_key=token) is not None

    def validate_request_token(self, client_key: str, token: str, request: oauthlib.common.Request) -> bool:
        req_tok = M.OAuthRequestToken.query.get(api_key=token)
        if not req_tok:
            return False
        return oauthlib.common.safe_string_equals(req_tok.consumer_token.api_key, client_key)

    def invalidate_request_token(self, client_key: str, request_token: str, request: oauthlib.common.Request) -> None:
        M.OAuthRequestToken.query.remove({'api_key': request_token})

    def validate_verifier(self, client_key: str, token: str, verifier: str, request: oauthlib.common.Request) -> bool:
        req_tok = M.OAuthRequestToken.query.get(api_key=token)
        return oauthlib.common.safe_string_equals(req_tok.validation_pin, verifier)  # NoneType error? you need dummy_oauths()

    def save_verifier(self, token: str, verifier: dict, request: oauthlib.common.Request) -> None:
        req_tok = M.OAuthRequestToken.query.get(api_key=token)
        req_tok.validation_pin = verifier['oauth_verifier']
        session(req_tok).flush(req_tok)

    def get_redirect_uri(self, token: str, request: oauthlib.common.Request) -> str:
        return M.OAuthRequestToken.query.get(api_key=token).callback

    def get_request_token_secret(self, client_key: str, token: str, request: oauthlib.common.Request) -> str:
        return M.OAuthRequestToken.query.get(api_key=token).secret_key  # NoneType error? you need dummy_oauths()

    def save_access_token(self, token: dict, request: oauthlib.common.Request) -> None:
        consumer_token = M.OAuthConsumerToken.query.get(api_key=request.client_key)
        request_token = M.OAuthRequestToken.query.get(api_key=request.resource_owner_key)
        tok = M.OAuthAccessToken(
            api_key=token['oauth_token'],
            secret_key=token['oauth_token_secret'],
            consumer_token_id=consumer_token._id,
            request_token_id=request_token._id,
            user_id=request_token.user_id,
        )
        session(tok).flush(tok)

    def validate_access_token(self, client_key: str, token: str, request: oauthlib.common.Request) -> bool:
        return M.OAuthAccessToken.query.get(api_key=token) is not None

    def get_access_token_secret(self, client_key: str, token: str, request: oauthlib.common.Request) -> str:
        return M.OAuthAccessToken.query.get(api_key=token).secret_key  # NoneType error? you need dummy_oauths()

    @property
    def enforce_ssl(self) -> bool:
        # don't enforce SSL in limited situations
        if request.environ.get('paste.testing'):
            # test suite is running
            return False
        elif asbool(config.get('debug')) and config['base_url'].startswith('http://'):  # noqa: SIM103
            # development w/o https
            return False
        else:
            return True

    @property
    def safe_characters(self):
        # add a few characters, so tests can have clear readable values
        return super().safe_characters | {'_', '-'}

    def get_default_realms(self, client_key, request):
        return []

    def validate_requested_realms(self, client_key, realms, request):
        return True

    def get_realms(self, token, request):
        return []

    def validate_realms(self, client_key, token, request, uri=None, realms=None) -> bool:
        return True

    def validate_timestamp_and_nonce(self, client_key, timestamp, nonce,
                                     request, request_token=None, access_token=None) -> bool:
        # TODO: record and check nonces from reuse
        return True

    def validate_redirect_uri(self, client_key, redirect_uri, request) -> bool:
        # TODO: have application owner specify redirect uris, save on OAuthConsumerToken
        return True

    @property
    def dummy_client(self) -> str:
        return 'dummy-client-key-for-oauthlib'

    @property
    def dummy_request_token(self) -> str:
        return 'dummy-request-token-for-oauthlib'

    @property
    def dummy_access_token(self) -> str:
        return 'dummy-access-token-for-oauthlib'


class Oauth2Validator(oauthlib.oauth2.RequestValidator):
    def __init__(self):
        super().__init__()
        if asbool(tg.config.get('debug')):
            oauthlib.set_debug(True)

    def validate_client_id(self, client_id: str, request: oauthlib.common.Request, *args, **kwargs) -> bool:
        return M.OAuth2ClientApp.query.get(client_id=client_id) is not None

    def validate_redirect_uri(self, client_id, redirect_uri, request, *args, **kwargs):
        if redirect_uri.startswith('http:'):
            return False
        client = M.OAuth2ClientApp.query.get(client_id=client_id)
        return redirect_uri in client.redirect_uris

    def validate_response_type(self, client_id: str, response_type: str, client: oauthlib.oauth2.Client, request: oauthlib.common.Request, *args, **kwargs) -> bool:
        res_type = M.OAuth2ClientApp.query.get(client_id=client_id).response_type
        return res_type == response_type

    def validate_scopes(self, client_id: str, scopes, client: oauthlib.oauth2.Client, request: oauthlib.common.Request, *args, **kwargs) -> bool:
        return True

    def validate_grant_type(self, client_id: str, grant_type: str, client: oauthlib.oauth2.Client, request: oauthlib.common.Request, *args, **kwargs) -> bool:
        return grant_type in ['authorization_code', 'refresh_token']

    def get_default_scopes(self, client_id: str, request: oauthlib.common.Request, *args, **kwargs):
        return []

    def get_original_scopes(self, refresh_token: str, request: oauthlib.common.Request, *args, **kwargs) -> list[str]:
        return None

    def get_default_redirect_uri(self, client_id: str, request: oauthlib.common.Request, *args, **kwargs) -> str:
        client = M.OAuth2ClientApp.query.get(client_id=client_id)
        return client.redirect_uris[0] if client.redirect_uris else None

    def is_pkce_required(self, client_id: str, request: oauthlib.common.Request) -> bool:
        return False

    def get_code_challenge(self, code: str, request: oauthlib.common.Request) -> str:
        authorization_code = M.OAuth2AuthorizationCode.query.get(authorization_code=code)
        return authorization_code.code_challenge

    def get_code_challenge_method(self, code: str, request: oauthlib.common.Request) -> str:
        authorization_code = M.OAuth2AuthorizationCode.query.get(authorization_code=code)
        return authorization_code.code_challenge_method

    def invalidate_authorization_code(self, client_id: str, code: str, request: oauthlib.common.Request, *args, **kwargs) -> None:
        M.OAuth2AuthorizationCode.query.remove({'client_id': client_id, 'authorization_code': code})

    def authenticate_client(self, request: oauthlib.common.Request, *args, **kwargs) -> bool:
        request.client = M.OAuth2ClientApp.query.get(client_id=request.client_id, client_secret=request.client_secret)
        return request.client is not None

    def validate_code(self, client_id: str, code: str, client: oauthlib.oauth2.Client, request: oauthlib.common.Request, *args, **kwargs) -> bool:
        authorization = M.OAuth2AuthorizationCode.query.get(client_id=client_id, authorization_code=code)
        return authorization.expires_at >= datetime.utcnow() if authorization else False

    def validate_bearer_token(self, token: str, scopes: list[str], request: oauthlib.common.Request) -> bool:
        access_token = M.OAuth2AccessToken.query.get(access_token=token)
        if access_token and access_token.expires_at >= datetime.utcnow():
            request.access_token = access_token
            return True
        else:
            return False

    def validate_refresh_token(self, refresh_token: str, client: oauthlib.oauth2.Client, request: oauthlib.common.Request, *args, **kwargs) -> bool:
        return M.OAuth2AccessToken.query.get(refresh_token=refresh_token, client_id=client.client_id) is not None

    def confirm_redirect_uri(self, client_id: str, code: str, redirect_uri: str, client: oauthlib.oauth2.Client, request: oauthlib.common.Request, *args, **kwargs) -> bool:
        # This method is called when the client is exchanging the authorization code for an access token.
        # If a redirect uri was provided when the authorization code was created, it must match the redirect uri provided here.
        authorization = M.OAuth2AuthorizationCode.query.get(client_id=client_id, authorization_code=code)
        return authorization.redirect_uri == redirect_uri

    def save_authorization_code(self, client_id: str, code, request: oauthlib.common.Request, *args, **kwargs) -> None:
        authorization = M.OAuth2AuthorizationCode.query.get(client_id=client_id, user_id=c.user._id)

        # Remove the existing authorization code if it exists and create a new record
        if authorization:
            M.OAuth2AuthorizationCode.query.remove({'client_id': client_id, 'user_id': c.user._id})

        log.info('Saving authorization code for client: %s', client_id)
        auth_code = M.OAuth2AuthorizationCode(
            client_id=client_id,
            authorization_code=code['code'],
            expires_at=datetime.utcnow() + timedelta(minutes=10),
            redirect_uri=request.redirect_uri,
            user_id=c.user._id,
            code_challenge=request.code_challenge,
            code_challenge_method=request.code_challenge_method
        )
        session(auth_code).flush()
        log.info(f'Saving new authorization code for client: {client_id}')

    def save_bearer_token(self, token, request: oauthlib.common.Request, *args, **kwargs) -> object:
        if request.grant_type == 'authorization_code':
            user_id = M.OAuth2AuthorizationCode.query.get(client_id=request.client_id, authorization_code=request.code).user_id
        elif request.grant_type == 'refresh_token':
            user_id = M.OAuth2AccessToken.query.get(client_id=request.client_id, refresh_token=request.refresh_token).user_id

        current_token = M.OAuth2AccessToken.query.get(client_id=request.client_id, user_id=user_id, is_bearer=False)

        if current_token:
            M.OAuth2AccessToken.query.remove({'client_id': request.client_id, 'user_id': user_id, 'is_bearer': False})

        bearer_token = M.OAuth2AccessToken(
            client_id=request.client_id,
            scopes=token.get('scope', []),
            access_token=token.get('access_token'),
            refresh_token=token.get('refresh_token'),
            expires_at=datetime.utcnow() + timedelta(seconds=token.get('expires_in')),
            user_id=user_id
        )

        session(bearer_token).flush()
        log.info(f'Saving new bearer token for client: {request.client_id}')


class AlluraOauth1Server(oauthlib.oauth1.WebApplicationServer):
    def validate_request_token_request(self, request):
        # this is NOT standard OAuth1 (spec requires the param)
        # but initial Allura implementation defaulted it to "oob" so we'll continue to do that
        # (this is called within create_request_token_response)
        if not request.redirect_uri:
            request.redirect_uri = 'oob'
        return super().validate_request_token_request(request)


class OAuthNegotiator:

    @property
    def server(self):
        return AlluraOauth1Server(Oauth1Validator())

    def _authenticate(self):
        bearer_token_prefix = 'Bearer '  # noqa: S105
        auth = request.headers.get('Authorization')
        if auth and auth.startswith(bearer_token_prefix):
            access_token = auth[len(bearer_token_prefix):]
        else:
            access_token = request.params.get('access_token')
        if access_token:
            # handle bearer tokens
            # skip https check if auth invoked from tests
            testing = request.environ.get('paste.testing', False)
            debug = asbool(config.get('debug', False))
            if not any((testing,
                        request.scheme == 'https',
                        request.environ.get('HTTP_X_FORWARDED_SSL') == 'on',
                        request.environ.get('HTTP_X_FORWARDED_PROTO') == 'https',
                        debug)):
                request.environ['tg.status_code_redirect'] = True
                raise exc.HTTPUnauthorized('HTTPS is required to use bearer tokens %s' % request.environ)
            access_token = M.OAuthAccessToken.query.get(api_key=access_token)
            if not (access_token and access_token.is_bearer):
                request.environ['tg.status_code_redirect'] = True
                raise exc.HTTPUnauthorized
            access_token.last_access = datetime.utcnow()
            return access_token

        provider = oauthlib.oauth1.ResourceEndpoint(Oauth1Validator())
        valid: bool
        oauth_req: oauthlib.common.Request
        valid, oauth_req = provider.validate_protected_resource_request(
            request.url,
            http_method=request.method,
            body=request.body,
            headers=request.headers,
            realms=[])
        if not valid:
            raise exc.HTTPUnauthorized

        access_token = M.OAuthAccessToken.query.get(api_key=oauth_req.oauth_params['oauth_token'])
        access_token.last_access = datetime.utcnow()
        return access_token

    @expose()
    def request_token(self, **kw):
        headers, body, status = self.server.create_request_token_response(
            request.url,
            http_method=request.method,
            body=request.body,
            headers=request.headers)
        response.headers.update(headers)
        response.status_int = status
        return body

    @expose('jinja:allura:templates/oauth_authorize.html')
    def authorize(self, **kwargs):
        security.require_authenticated()

        try:
            realms, credentials = self.server.get_realms_and_credentials(
                request.url,
                http_method=request.method,
                body=request.body,
                headers=request.headers)
        except oauthlib.oauth1.OAuth1Error as oae:
            log.info(f'oauth1 authorize error: {oae!r}')
            response.headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            response.status_int = oae.status_code
            body = oae.urlencoded
            return body
        oauth_token = credentials.get('resource_owner_key', 'unknown')

        rtok = M.OAuthRequestToken.query.get(api_key=oauth_token)
        if rtok is None:
            log.error('Invalid token %s', oauth_token)
            raise exc.HTTPUnauthorized
        # store what user this is, so later use of the token can act as them
        rtok.user_id = c.user._id
        return dict(
            oauth_token=oauth_token,
            consumer=rtok.consumer_token)

    @expose('jinja:allura:templates/oauth_authorize_ok.html')
    @require_post()
    def do_authorize(self, yes=None, no=None, oauth_token=None):
        security.require_authenticated()

        rtok = M.OAuthRequestToken.query.get(api_key=oauth_token)
        if no:
            rtok.delete()
            flash('%s NOT AUTHORIZED' % rtok.consumer_token.name, 'error')
            redirect('/auth/oauth/')

        headers, body, status = self.server.create_authorization_response(
            request.url,
            http_method=request.method,
            body=request.body,
            headers=request.headers,
            realms=[])

        if status == 200:
            verifier = str(parse_qs(body)['oauth_verifier'][0])
            rtok.validation_pin = verifier
            return dict(rtok=rtok)
        else:
            response.headers.update(headers)
            response.status_int = status
            return body

    @expose()
    def access_token(self, **kw):
        headers, body, status = self.server.create_access_token_response(
            request.url,
            http_method=request.method,
            body=request.body,
            headers=request.headers)
        response.headers.update(headers)
        response.status_int = status
        return body


class Oauth2Negotiator:
    @property
    def server(self):
        return oauthlib.oauth2.WebApplicationServer(Oauth2Validator())

    def _authenticate(self):
        valid, req = self.server.verify_request(
            request.url,
            http_method=request.method,
            body=request.body,
            headers=request.headers)

        if not valid:
            raise exc.HTTPUnauthorized

        token = req.access_token  # set by validate_bearer_token
        token.last_access = datetime.utcnow()
        return token

    @expose('json:')
    @require_post()
    def token(self, **kwargs):
        decoded_body = str(request.body, 'utf-8')

        # We try to parse the request body as JSON, if it fails we just use the body as is
        # so it's treated as x-www-form-urlencoded
        try:
            request_body = json.loads(decoded_body)
        except json.decoder.JSONDecodeError:
            request_body = decoded_body

        headers, body, status = self.server.create_token_response(uri=request.url, http_method=request.method, body=request_body, headers=request.headers)
        response.headers.update(headers)
        response.status_int = status
        return body

def rest_has_access(obj, user, perm):
    """
    Helper function that encapsulates common functionality for has_access API
    """
    security.require_access(obj, 'admin')
    resp = {'result': False}
    user = M.User.by_username(user)
    if user:
        resp['result'] = security.has_access(obj, perm, user=user)
    return resp


class AppRestControllerMixin:
    @expose('json:')
    def has_access(self, user, perm, **kw):
        return rest_has_access(c.app, user, perm)


def nbhd_lookup_first_path(nbhd, name, current_user, remainder, api=False):
    """
    Resolve first part of a neighborhood url.  May raise 404, redirect, or do other side effects.

    Shared between NeighborhoodController and NeighborhoodRestController

    :param nbhd: neighborhood
    :param name: project or tool name (next part of url)
    :param current_user: a User
    :param remainder: remainder of url
    :param bool api: whether this is handling a /rest/ request or not

    :return: project (to be set as c.project)
    :return: remainder (possibly modified)
    """

    prefix = nbhd.shortname_prefix
    pname = unquote(name)
    pname = six.ensure_text(pname)  # we don't support unicode names, but in case a url comes in with one
    try:
        pname.encode('ascii')
    except UnicodeError:
        raise exc.HTTPNotFound
    provider = plugin.ProjectRegistrationProvider.get()
    try:
        provider.shortname_validator.to_python(pname, check_allowed=False, neighborhood=nbhd, permit_legacy=True)
    except Invalid:
        project = None
    else:
        project = M.Project.query.get(shortname=prefix + pname, neighborhood_id=nbhd._id)
    if project is None and prefix == 'u/':
        # create user-project if it is missing
        user = M.User.query.get(username=pname, disabled=False, pending=False)
        if user:
            project = user.private_project()
    if project is None:
        # look for neighborhood tools matching the URL
        project = nbhd.neighborhood_project
        return project, (pname,) + remainder  # include pname in new remainder, it is actually the nbhd tool path
    if project and prefix == 'u/':
        # make sure user-projects are associated with an enabled user
        is_site_admin = h.is_site_admin(c.user)
        user = project.get_userproject_user(include_disabled=is_site_admin)
        if not user or user.pending:
            raise exc.HTTPNotFound
        if user.disabled and not is_site_admin:
            raise exc.HTTPNotFound
        if not api and user.url() != f'/{prefix}{pname}/':
            # might be different URL than the URL requested
            # e.g. if username isn't valid project name and user_project_shortname() converts the name
            new_url = user.url()
            new_url += '/'.join(remainder)
            if request.query_string:
                new_url += '?' + request.query_string
            redirect(new_url)
    if project.database_configured is False:
        if remainder == ('user_icon',):
            redirect(g.forge_static('images/user.png'))
        elif current_user.username == pname:
            log.info('Configuring %s database for access to %r', pname, remainder)
            project.configure_project(is_user_project=True)
        else:
            raise exc.HTTPNotFound(pname)
    if project is None or (project.deleted and not has_access(project, 'update')):
        raise exc.HTTPNotFound(pname)
    return project, remainder


class NeighborhoodRestController:

    def __init__(self, neighborhood):
        # type: (M.Neighborhood) -> None
        self._neighborhood = neighborhood

    @expose('json:')
    def has_access(self, user, perm, **kw):
        return rest_has_access(self._neighborhood, user, perm)

    @expose()
    def _lookup(self, name=None, *remainder):
        if not name:
            raise exc.HTTPNotFound
        c.project, remainder = nbhd_lookup_first_path(self._neighborhood, name, c.user, remainder, api=True)
        return ProjectRestController(), remainder

    @expose('json:')
    @require_post()
    def add_project(self, **kw):
        # TODO: currently limited to 'admin' permissions instead of 'register' since not enough validation is in place.
        # There is sanity checks and validation that the user may create a project, but not on project fields
        #   for example: tool_data, admins, awards, etc can be set arbitrarily right now
        #   and normal fields like description, summary, external_homepage, troves etc don't have validation on length,
        #   quantity, value etc. which match the HTML web form validations
        # if/when this is handled better, the following line can be updated.  Also update api.raml docs
        # security.require_access(self._neighborhood, 'register')
        security.require_access(self._neighborhood, 'admin')

        project_reg = plugin.ProjectRegistrationProvider.get()

        jsondata = json.loads(request.body)
        projectSchema = make_newproject_schema(self._neighborhood)
        try:
            pdata = deserialize_project(jsondata, projectSchema, self._neighborhood)
            shortname = pdata.shortname
            project_reg.validate_project(self._neighborhood, shortname, pdata.name, c.user,
                                         user_project=False, private_project=pdata.private)
        except (colander.Invalid, ForgeError) as e:
            response.status_int = 400
            return {
                'error': str(e) or repr(e),
            }

        project = create_project_with_attrs(pdata, self._neighborhood)
        response.status_int = 201
        response.location = str(h.absurl('/rest' + project.url()))
        return {
            "status": "success",
            "html_url": h.absurl(project.url()),
            "url": h.absurl('/rest' + project.url()),
        }


class ProjectRestController:

    @expose()
    def _lookup(self, name, *remainder):
        if not name:
            return self, ()
        subproject = M.Project.query.get(
            shortname=c.project.shortname + '/' + name,
            neighborhood_id=c.project.neighborhood_id,
            deleted=False)
        if subproject:
            c.project = subproject
            c.app = None
            return ProjectRestController(), remainder
        app = c.project.app_instance(name)
        if app is None:
            raise exc.HTTPNotFound(name)
        c.app = app
        if app.api_root is None:
            raise exc.HTTPNotFound(name)
        return app.api_root, remainder

    @expose('json:')
    def index(self, **kw):
        if 'doap' in kw:
            response.headers['Content-Type'] = ''
            response.content_type = 'application/rdf+xml'
            return b'<?xml version="1.0" encoding="UTF-8" ?>' + c.project.doap()
        return c.project.__json__()

    @expose('json:')
    def has_access(self, user, perm, **kw):
        return rest_has_access(c.project, user, perm)
