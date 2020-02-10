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
import logging

import oauth2 as oauth
from tg import tmpl_context as c, app_globals as g

from paste.deploy.converters import aslist
from tg import config
import pymongo
from ming import schema as S
from ming.orm import FieldProperty, RelationProperty, ForeignIdProperty, session
from ming.orm.declarative import MappedClass

from allura.lib import helpers as h
from .session import main_orm_session
from .types import MarkdownCache
from .auth import AlluraUserProperty

log = logging.getLogger(__name__)


class OAuthToken(MappedClass):

    class __mongometa__:
        session = main_orm_session
        name = str('oauth_token')
        indexes = ['api_key']
        polymorphic_on = 'type'
        polymorphic_identity = None

    _id = FieldProperty(S.ObjectId)
    type = FieldProperty(str)
    api_key = FieldProperty(str, if_missing=lambda: h.nonce(20))
    secret_key = FieldProperty(str, if_missing=h.cryptographic_nonce)

    def to_string(self):
        return oauth.Token(self.api_key, self.secret_key).to_string()

    def as_token(self):
        return oauth.Token(self.api_key, self.secret_key)


class OAuthConsumerToken(OAuthToken):

    class __mongometa__:
        polymorphic_identity = str('consumer')
        name = str('oauth_consumer_token')
        unique_indexes = [('name', 'user_id')]

    type = FieldProperty(str, if_missing='consumer')
    user_id = AlluraUserProperty(if_missing=lambda: c.user._id)
    name = FieldProperty(str)
    description = FieldProperty(str, if_missing='')
    description_cache = FieldProperty(MarkdownCache)

    user = RelationProperty('User')

    @property
    def description_html(self):
        return g.markdown.cached_convert(self, 'description')

    @property
    def consumer(self):
        '''OAuth compatible consumer object'''
        return oauth.Consumer(self.api_key, self.secret_key)

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
        polymorphic_identity = str('request')

    type = FieldProperty(str, if_missing='request')
    consumer_token_id = ForeignIdProperty('OAuthConsumerToken')
    user_id = AlluraUserProperty(if_missing=lambda: c.user._id)
    callback = FieldProperty(str)
    validation_pin = FieldProperty(str)

    consumer_token = RelationProperty('OAuthConsumerToken')


class OAuthAccessToken(OAuthToken):

    class __mongometa__:
        polymorphic_identity = str('access')

    type = FieldProperty(str, if_missing='access')
    consumer_token_id = ForeignIdProperty('OAuthConsumerToken')
    request_token_id = ForeignIdProperty('OAuthToken')
    user_id = AlluraUserProperty(if_missing=lambda: c.user._id)
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
