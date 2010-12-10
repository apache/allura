import os
import re
import logging
import urllib
import hmac
import hashlib
from datetime import timedelta, datetime
from hashlib import sha256

import iso8601
import pymongo
from pylons import c, g, request

from ming import schema as S
from ming.orm.ormsession import ThreadLocalORMSession
from ming.orm import session, state, MappedClass
from ming.orm import FieldProperty, RelationProperty, ForeignIdProperty

from allura.lib import helpers as h
from allura.lib import plugin
from .session import ProjectSession
from .session import main_doc_session, main_orm_session
from .session import project_doc_session, project_orm_session

log = logging.getLogger(__name__)

class OAuthConsumerToken(MappedClass):
    class __mongometa__:
        name='oauth_consumer_token'
        session = main_orm_session
        indexes = [ 'api_key' ]
        unique_indexes = [ 'name' ]

    _id = FieldProperty(S.ObjectId)
    user_id = ForeignIdProperty('User', if_missing=lambda:c.user._id)
    name = FieldProperty(str)
    description = FieldProperty(str)
    api_key = FieldProperty(str, if_missing=lambda:h.nonce(20))
    secret_key = FieldProperty(str, if_missing=h.cryptographic_nonce)
    
    user = RelationProperty('User')

    @property
    def description_html(self):
        return g.markdown.convert(self.description)

    @classmethod
    def for_user(cls, user=None):
        if user is None: user = c.user
        return cls.query.find(dict(user_id=user._id)).all()

class OAuthAccessToken(MappedClass):
    class __mongometa__:
        name='oauth_request_token'
    _id = FieldProperty(S.ObjectId)
    user_id = ForeignIdProperty('User')
    api_key = FieldProperty(str, if_missing=lambda:h.nonce(20))
    secret_key = FieldProperty(str, if_missing=h.cryptographic_nonce)

    user = RelationProperty('User')
