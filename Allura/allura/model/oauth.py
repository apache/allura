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

import logging
import typing
from datetime import datetime

from tg import tmpl_context as c, app_globals as g

from paste.deploy.converters import aslist
from tg import config
import pymongo
from ming import schema as S
from ming.odm import FieldProperty, RelationProperty, ForeignIdProperty, session
from ming.odm.declarative import MappedClass
from bson import ObjectId

from allura.lib import helpers as h
from .session import main_orm_session
from .types import MarkdownCache
from .auth import AlluraUserProperty

if typing.TYPE_CHECKING:
    from ming.odm.mapper import Query


log = logging.getLogger(__name__)


class OAuthToken(MappedClass):

    class __mongometa__:
        session = main_orm_session
        name = 'oauth_token'
        unique_indexes = ['api_key']
        indexes = [
            ('user_id'),
        ]
        polymorphic_on = 'type'
        polymorphic_identity = None

    query: 'Query[OAuthToken]'

    _id = FieldProperty(S.ObjectId)
    type = FieldProperty(str)
    api_key = FieldProperty(str, if_missing=lambda: h.nonce(20))
    secret_key = FieldProperty(str, if_missing=h.cryptographic_nonce)
    last_access = FieldProperty(datetime)


class OAuthConsumerToken(OAuthToken):

    class __mongometa__:
        polymorphic_identity = 'consumer'
        name = 'oauth_consumer_token'
        unique_indexes = [
            ('name', 'user_id'),
            ('api_key',),
        ]

    query: 'Query[OAuthConsumerToken]'

    type = FieldProperty(str, if_missing='consumer')
    user_id: ObjectId = AlluraUserProperty(if_missing=lambda: c.user._id)
    name = FieldProperty(str)
    description = FieldProperty(str, if_missing='')
    description_cache = FieldProperty(MarkdownCache)

    user = RelationProperty('User')

    @property
    def description_html(self):
        return g.markdown.cached_convert(self, 'description')

    @classmethod
    def upsert(cls, name, user):
        params = dict(name=name, user_id=user._id)
        t = cls.query.get(**params)
        if t is not None:
            return t
        try:
            t = cls(**params)
            session(t).flush(t)
        except pymongo.errors.DuplicateKeyError:
            session(t).expunge(t)
            t = cls.query.get(**params)
        return t

    @classmethod
    def for_user(cls, user=None):
        if user is None:
            user = c.user
        return cls.query.find(dict(user_id=user._id)).all()


class OAuthRequestToken(OAuthToken):

    class __mongometa__:
        polymorphic_identity = 'request'

    query: 'Query[OAuthRequestToken]'

    type = FieldProperty(str, if_missing='request')
    consumer_token_id = ForeignIdProperty('OAuthConsumerToken')
    user_id: ObjectId = AlluraUserProperty(if_missing=lambda: c.user._id)
    callback = FieldProperty(str)
    validation_pin = FieldProperty(str)

    consumer_token: OAuthConsumerToken = RelationProperty('OAuthConsumerToken')


class OAuthAccessToken(OAuthToken):

    class __mongometa__:
        polymorphic_identity = 'access'

    query: 'Query[OAuthAccessToken]'

    type = FieldProperty(str, if_missing='access')
    consumer_token_id = ForeignIdProperty('OAuthConsumerToken')
    request_token_id = ForeignIdProperty('OAuthToken')
    user_id: ObjectId = AlluraUserProperty(if_missing=lambda: c.user._id)
    is_bearer = FieldProperty(bool, if_missing=False)

    user = RelationProperty('User')
    consumer_token = RelationProperty(
        'OAuthConsumerToken', via='consumer_token_id')
    request_token = RelationProperty('OAuthToken', via='request_token_id')

    @classmethod
    def for_user(cls, user=None):
        if user is None:
            user = c.user
        return cls.query.find(dict(user_id=user._id, type='access')).all()

    def can_import_forum(self):
        tokens = aslist(config.get('oauth.can_import_forum', ''), ',')
        if self.api_key in tokens:
            return True
        return False


class OAuth2ClientApp(MappedClass):
    class __mongometa__:
        session = main_orm_session
        name = 'oauth2_client_app'
        unique_indexes = [('client_id', 'owner_id')]

    query: 'Query[OAuth2ClientApp]'

    _id = FieldProperty(S.ObjectId)
    client_id = FieldProperty(str, if_missing=lambda: h.nonce(20))
    credentials = FieldProperty(S.Anything)
    name = FieldProperty(str)
    description = FieldProperty(str, if_missing='')
    description_cache = FieldProperty(MarkdownCache)
    owner_id: ObjectId = AlluraUserProperty(if_missing=lambda: c.user._id)
    grant_type = FieldProperty(str, if_missing='authorization_code')
    response_type = FieldProperty(str, if_missing='code')
    scopes = FieldProperty([str])
    redirect_uris = FieldProperty([str])

    owner = RelationProperty('User')


    @classmethod
    def for_owner(cls, owner=None):
        if owner is None:
            owner = c.user
        return cls.query.find(dict(owner_id=owner._id)).all()

    @classmethod
    def set_credentials(cls, client_id, credentials):
        cls.query.update({'client_id': client_id }, {'$set': {'credentials': credentials}})

    @property
    def description_html(self):
        return g.markdown.cached_convert(self, 'description')


class OAuth2AuthorizationCode(MappedClass):
    class __mongometa__:
        session = main_orm_session
        name = 'oauth2_authorization_code'
        unique_indexes = [('authorization_code', 'client_id', 'owner_id')]

    query: 'Query[OAuth2AuthorizationCode]'

    _id = FieldProperty(S.ObjectId)
    client_id = FieldProperty(str)
    owner_id: ObjectId = AlluraUserProperty(if_missing=lambda: c.user._id)
    scopes = FieldProperty([str])
    redirect_uri = FieldProperty(str)
    authorization_code = FieldProperty(str)
    expires_at = FieldProperty(S.DateTime)
    # For PKCE support
    code_challenge = FieldProperty(str)
    code_challenge_method = FieldProperty(str)

    owner = RelationProperty('User')


class OAuth2AccessToken(MappedClass):
    class __mongometa__:
        session = main_orm_session
        name = 'oauth2_access_token'
        unique_indexes = [('access_token', 'client_id', 'owner_id')]

    query: 'Query[OAuth2AccessToken]'

    _id = FieldProperty(S.ObjectId)
    client_id = FieldProperty(str)
    owner_id: ObjectId = AlluraUserProperty(if_missing=lambda: c.user._id)
    scopes = FieldProperty([str])
    access_token = FieldProperty(str)
    refresh_token = FieldProperty(str)
    expires_at = FieldProperty(S.DateTime)
    last_access = FieldProperty(datetime)

    owner = RelationProperty('User')


def dummy_oauths():
    from allura.controllers.rest import Oauth1Validator
    # oauthlib implementation NEEDS these "dummy" values.  If a request comes in with an invalid param, it runs
    # the regular oauth methods but using these dummy values, so that everything takes constant time
    # so these need to exist in the database even though they're called "dummy" values
    dummy_cons_tok = OAuthConsumerToken(
        api_key=Oauth1Validator().dummy_client,
        name='dummy client, for oauthlib implementation',
        user_id=None,
    )
    session(dummy_cons_tok).flush(dummy_cons_tok)
    dummy_req_tok = OAuthRequestToken(
        api_key=Oauth1Validator().dummy_request_token,
        user_id=None,
        validation_pin='dummy-pin',
    )
    session(dummy_req_tok).flush(dummy_req_tok)
    dummy_access_tok = OAuthAccessToken(
        api_key=Oauth1Validator().dummy_access_token,
        user_id=None,
    )
    session(dummy_access_tok).flush(dummy_access_tok)