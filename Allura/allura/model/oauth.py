import logging

import oauth2 as oauth
from pylons import c, g

from ming import schema as S
from ming.orm import FieldProperty, RelationProperty, ForeignIdProperty
from ming.orm.declarative import MappedClass

from allura.lib import helpers as h
from .session import main_doc_session, main_orm_session
from .session import project_doc_session, project_orm_session

log = logging.getLogger(__name__)

class OAuthToken(MappedClass):
    class __mongometa__:
        session = main_orm_session
        name='oauth_token'
        indexes = [ 'api_key' ]
        polymorphic_on='type'
        polymorphic_identity=None

    _id = FieldProperty(S.ObjectId)
    type=FieldProperty(str)
    api_key = FieldProperty(str, if_missing=lambda:h.nonce(20))
    secret_key = FieldProperty(str, if_missing=h.cryptographic_nonce)

    def to_string(self):
        return oauth.Token(self.api_key, self.secret_key).to_string()

    def as_token(self):
        return oauth.Token(self.api_key, self.secret_key)

class OAuthConsumerToken(OAuthToken):
    class __mongometa__:
        polymorphic_identity='consumer'
        name='oauth_consumer_token'
        unique_indexes = [ 'name' ]

    type = FieldProperty(str, if_missing='consumer')
    user_id = ForeignIdProperty('User', if_missing=lambda:c.user._id)
    name = FieldProperty(str)
    description = FieldProperty(str)
    
    user = RelationProperty('User')

    @property
    def description_html(self):
        return g.markdown.convert(self.description)

    @property
    def consumer(self):
        '''OAuth compatible consumer object'''
        return oauth.Consumer(self.api_key, self.secret_key)

    @classmethod
    def for_user(cls, user=None):
        if user is None: user = c.user
        return cls.query.find(dict(user_id=user._id)).all()

class OAuthRequestToken(OAuthToken):
    class __mongometa__:
        polymorphic_identity='request'

    type = FieldProperty(str, if_missing='request')
    consumer_token_id = ForeignIdProperty('OAuthConsumerToken')
    user_id = ForeignIdProperty('User', if_missing=lambda:c.user._id)
    callback = FieldProperty(str)
    validation_pin = FieldProperty(str)

    consumer_token = RelationProperty('OAuthConsumerToken')

class OAuthAccessToken(OAuthToken):
    class __mongometa__:
        polymorphic_identity='access'

    type = FieldProperty(str, if_missing='access')
    consumer_token_id = ForeignIdProperty('OAuthConsumerToken')
    request_token_id = ForeignIdProperty('OAuthToken')
    user_id = ForeignIdProperty('User', if_missing=lambda:c.user._id)

    user = RelationProperty('User')
    consumer_token = RelationProperty('OAuthConsumerToken', via='consumer_token_id')
    request_token = RelationProperty('OAuthToken', via='request_token_id')

    @classmethod
    def for_user(cls, user=None):
        if user is None: user = c.user
        return cls.query.find(dict(user_id=user._id)).all()

