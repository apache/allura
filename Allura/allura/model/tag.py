import logging
import warnings
from datetime import datetime

from pylons import c, g, request
import pkg_resources
from webob import exc
from pymongo import bson

from ming import schema as S
from ming.orm.base import mapper, session
from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty, RelationProperty, ForeignIdProperty
from ming.orm.ormsession import ThreadLocalORMSession

from allura.lib.helpers import push_config
from .session import main_orm_session
from .types import ArtifactReferenceType

log = logging.getLogger(__name__)

class Tag(MappedClass):
    class __mongometa__:
        session = main_orm_session
        name='tag'

    _id = FieldProperty(S.ObjectId)
    user_id = ForeignIdProperty('User', if_missing=lambda:c.user._id)
    artifact_ref = FieldProperty(ArtifactReferenceType)
    tag = FieldProperty(str)

    @classmethod
    def add(cls, artifact_ref, user, tags):
        for t in tags:
            if cls.query.find(dict(
                    user_id=user._id,
                    artifact_ref=artifact_ref,
                    tag=t)).count(): continue
            else:
                cls(user_id=user._id,
                    artifact_ref=artifact_ref,
                    tag=t)

    @classmethod
    def remove(cls, artifact_ref, user, tags):
        cls.query.remove(dict(
                user_id=user._id,
                artifact_ref=artifact_ref,
                tag={'$in':tags}))

class TagEvent(MappedClass):
    class __mongometa__:
        session = main_orm_session
        name='tag_event'

    _id = FieldProperty(S.ObjectId)
    when = FieldProperty(datetime, if_missing=datetime.utcnow)
    user_id = ForeignIdProperty('User', if_missing=lambda:c.user._id)
    artifact_ref = FieldProperty(ArtifactReferenceType)
    added_tags = FieldProperty([str])
    removed_tags = FieldProperty([str])
    user = RelationProperty('User', via='user_id')

    def as_message(self):
        aref = self.artifact_ref
        aref['project_id'] = str(aref['project_id'])
        aref['artifact_id'] = str(aref['artifact_id'])
        d = dict(
            when=self.when,
            user_id=str(self.user_id),
            project_id=aref['project_id'],
            artifact_ref=dict(aref),
            added_tags=list(self.added_tags),
            removed_tags=list(self.removed_tags))
        return d

class UserTags(MappedClass):
    class __mongometa__:
        session = main_orm_session
        name = 'user_tags'

    _id = FieldProperty(S.ObjectId)
    user_id = ForeignIdProperty('User')
    artifact_reference = FieldProperty(ArtifactReferenceType)
    tags = FieldProperty([dict(tag=str, when=datetime)])

    @classmethod
    def upsert(cls, user, artifact_ref):
        obj = cls.query.get(user_id=user._id, artifact_reference=artifact_ref)
        if obj is None: obj = cls(user_id=user._id, artifact_reference=artifact_ref)
        return obj

    def add_tags(self, when, tags):
        'Update the tags collection to reflect new tags added.  Called ONLY by reactors.'
        cur_tags = dict((t['tag'], t['when']) for t in self.tags)
        for t in tags:
            cur_tags[t] = when
        self.tags = [ dict(tag=k, when=v) for k,v in cur_tags.iteritems() ]

    def remove_tags(self, tags):
        'Update the tags collection to reflect tags removed.  Called ONLY by reactors.'
        cur_tags = dict((t['tag'], t['when']) for t in self.tags)
        for t in tags:
            cur_tags.pop(t, None)
        self.tags = [ dict(tag=k, when=v) for k,v in cur_tags.iteritems() ]
        if not self.tags:
            self.delete()
