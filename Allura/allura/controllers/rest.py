# -*- coding: utf-8 -*-

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
from __future__ import unicode_literals
from __future__ import absolute_import
import logging
from six.moves.urllib.parse import unquote

import oauth2 as oauth
from paste.util.converters import asbool
from webob import exc
from tg import expose, flash, redirect, config
from tg import tmpl_context as c, app_globals as g
from tg import request, response

from ming.orm import session
from ming.utils import LazyProperty

from allura import model as M
from allura.lib import helpers as h
from allura.lib import security
from allura.lib import plugin
from allura.lib.exceptions import Invalid
from allura.lib.decorators import require_post
from allura.lib.security import has_access
import six

log = logging.getLogger(__name__)


class RestController(object):

    def __init__(self):
        self.oauth = OAuthNegotiator()

    def _authenticate_request(self):
        'Based on request.params or oauth, authenticate the request'
        headers_auth = 'Authorization' in request.headers
        params_auth = 'oauth_token' in request.params
        params_auth = params_auth or 'access_token' in request.params
        if headers_auth or params_auth:
            return self.oauth._authenticate()
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
        for stat, provider in six.iteritems(g.entry_points['site_stats']):
            stats[stat] = provider()
        if stats:
            summary['site_stats'] = stats
        return summary

    @expose('json:')
    def notification(self, cookie='', url='', tool_name='', **kw):
        c.api_token = self._authenticate_request()
        user = c.api_token.user if c.api_token else c.user
        r = g.theme._get_site_notification(
            url=url,
            user=user,
            tool_name=tool_name,
            site_notification_cookie_value=cookie
        )
        if r:
            return dict(notification=r[0], cookie=r[1])
        return {}

    @expose()
    def _lookup(self, name, *remainder):
        c.api_token = self._authenticate_request()
        if c.api_token:
            c.user = c.api_token.user
        neighborhood = M.Neighborhood.query.get(url_prefix='/' + name + '/')
        if not neighborhood:
            raise exc.HTTPNotFound(name)
        return NeighborhoodRestController(neighborhood), remainder


class OAuthNegotiator(object):

    @property
    def server(self):
        result = oauth.Server()
        result.add_signature_method(oauth.SignatureMethod_PLAINTEXT())
        result.add_signature_method(oauth.SignatureMethod_HMAC_SHA1())
        return result

    def _authenticate(self):
        bearer_token_prefix = 'Bearer '
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
            return access_token
        req = oauth.Request.from_request(
            request.method,
            request.url.split('?')[0],
            headers=request.headers,
            parameters=dict(request.params),
            query_string=request.query_string
        )
        consumer_token = M.OAuthConsumerToken.query.get(api_key=req['oauth_consumer_key'])
        access_token = M.OAuthAccessToken.query.get(api_key=req['oauth_token'])
        if consumer_token is None:
            log.error('Invalid consumer token')
            return None
        if access_token is None:
            log.error('Invalid access token')
            raise exc.HTTPUnauthorized
        consumer = consumer_token.consumer
        try:
            self.server.verify_request(req, consumer, access_token.as_token())
        except oauth.Error as e:
            log.error('Invalid signature %s %s', type(e), e)
            raise exc.HTTPUnauthorized
        return access_token

    @expose()
    def request_token(self, **kw):
        req = oauth.Request.from_request(
            request.method,
            request.url.split('?')[0],
            headers=request.headers,
            parameters=dict(request.params),
            query_string=request.query_string
        )
        consumer_token = M.OAuthConsumerToken.query.get(
            api_key=req['oauth_consumer_key'])
        if consumer_token is None:
            log.error('Invalid consumer token')
            raise exc.HTTPUnauthorized
        consumer = consumer_token.consumer
        try:
            self.server.verify_request(req, consumer, None)
        except oauth.Error as e:
            log.error('Invalid signature %s %s', type(e), e)
            raise exc.HTTPUnauthorized
        req_token = M.OAuthRequestToken(
            consumer_token_id=consumer_token._id,
            callback=req.get('oauth_callback', 'oob')
        )
        session(req_token).flush()
        log.info('Saving new request token with key: %s', req_token.api_key)
        return req_token.to_string()

    @expose('jinja:allura:templates/oauth_authorize.html')
    def authorize(self, oauth_token=None):
        security.require_authenticated()
        rtok = M.OAuthRequestToken.query.get(api_key=oauth_token)
        if rtok is None:
            log.error('Invalid token %s', oauth_token)
            raise exc.HTTPUnauthorized
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
        if rtok.callback == 'oob':
            rtok.validation_pin = h.nonce(6)
            return dict(rtok=rtok)
        rtok.validation_pin = h.nonce(20)
        if '?' in rtok.callback:
            url = rtok.callback + '&'
        else:
            url = rtok.callback + '?'
        url += 'oauth_token=%s&oauth_verifier=%s' % (
            rtok.api_key, rtok.validation_pin)
        redirect(url)

    @expose()
    def access_token(self, **kw):
        req = oauth.Request.from_request(
            request.method,
            request.url.split('?')[0],
            headers=request.headers,
            parameters=dict(request.params),
            query_string=request.query_string
        )
        consumer_token = M.OAuthConsumerToken.query.get(
            api_key=req['oauth_consumer_key'])
        request_token = M.OAuthRequestToken.query.get(
            api_key=req['oauth_token'])
        if consumer_token is None:
            log.error('Invalid consumer token')
            raise exc.HTTPUnauthorized
        if request_token is None:
            log.error('Invalid request token')
            raise exc.HTTPUnauthorized
        pin = req['oauth_verifier']
        if pin != request_token.validation_pin:
            log.error('Invalid verifier')
            raise exc.HTTPUnauthorized
        rtok = request_token.as_token()
        rtok.set_verifier(pin)
        consumer = consumer_token.consumer
        try:
            self.server.verify_request(req, consumer, rtok)
        except oauth.Error as e:
            log.error('Invalid signature %s %s', type(e), e)
            raise exc.HTTPUnauthorized
        acc_token = M.OAuthAccessToken(
            consumer_token_id=consumer_token._id,
            request_token_id=request_token._id,
            user_id=request_token.user_id,
        )
        return acc_token.to_string()


def rest_has_access(obj, user, perm):
    """
    Helper function that encapsulates common functionality for has_access API
    """
    security.require_access(obj, 'admin')
    resp = {'result': False}
    user = M.User.by_username(user)
    if user:
        resp['result'] = security.has_access(obj, perm, user=user)()
    return resp


class AppRestControllerMixin(object):
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
    provider = plugin.ProjectRegistrationProvider.get()
    try:
        provider.shortname_validator.to_python(pname, check_allowed=False, neighborhood=nbhd)
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
        return project, (pname.encode('utf-8'),) + remainder  # include pname in new remainder, it is actually the nbhd tool path
    if project and prefix == 'u/':
        # make sure user-projects are associated with an enabled user
        user = project.user_project_of
        if not user or user.disabled or user.pending:
            raise exc.HTTPNotFound
        if not api and user.url() != '/{}{}/'.format(prefix, pname):
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
    if project is None or (project.deleted and not has_access(project, 'update')()):
        raise exc.HTTPNotFound(pname)
    return project, remainder


class NeighborhoodRestController(object):

    def __init__(self, neighborhood):
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


class ProjectRestController(object):

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
            response.headers['Content-Type'] = str('')
            response.content_type = str('application/rdf+xml')
            return '<?xml version="1.0" encoding="UTF-8" ?>' + c.project.doap()
        return c.project.__json__()

    @expose('json:')
    def has_access(self, user, perm, **kw):
        return rest_has_access(c.project, user, perm)
