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

from pyforge.lib.helpers import push_config
from .session import main_orm_session, tag_event_orm_session

log = logging.getLogger(__name__)

ArtifactReference = S.Object(dict(
        project_id=S.ObjectId(if_missing=lambda:c.project._id),
        mount_point=S.String(if_missing=lambda:c.app.config.options.mount_point),
        artifact_type=str, # pickled class
        artifact_id=None))

class Tag(MappedClass):
    class __mongometa__:
        session = main_orm_session
        name='tag'

    _id = FieldProperty(S.ObjectId)
    user_id = ForeignIdProperty('User', if_missing=lambda:c.user._id)
    artifact_ref = FieldProperty(ArtifactReference)
    tag = FieldProperty(str)

    @classmethod
    def add(cls, artifact_ref, tags):
        for t in tags:
            if cls.query.find(dict(
                    user_id=c.user._id,
                    artifact_ref=artifact_ref,
                    tag=t)).count(): continue
            else:
                cls(user_id=c.user._id,
                    artifact_ref=artifact_ref,
                    tag=t)

    @classmethod
    def remove(cls, artifact_ref, tags):
        cls.query.remove(dict(
                user_id=c.user._id,
                artifact_ref=artifact_ref,
                tag={'$in':tags}))

class TagEvent(MappedClass):
    class __mongometa__:
        session = tag_event_orm_session
        name='tag_event'

    _id = FieldProperty(S.ObjectId)
    when = FieldProperty(datetime, if_missing=datetime.utcnow)
    event = FieldProperty(S.OneOf('add', 'remove'))
    user_id = ForeignIdProperty('User', if_missing=lambda:c.user._id)
    artifact_ref = FieldProperty(ArtifactReference)
    tags = FieldProperty([str])

    @classmethod
    def add(cls, artifact, tags):
        return cls(event='add', artifact_ref=artifact.dump_ref(), tags=tags)

    @classmethod
    def remove(cls, artifact, tags):
        return cls(event='remove', artifact_ref=artifact.dump_ref(), tags=tags)

    def as_message(self):
        aref = self.artifact_ref
        aref['project_id'] = str(aref['project_id'])
        aref['artifact_id'] = str(aref['artifact_id'])
        d = dict(
            when=self.when,
            event=self.event,
            user_id=self.user_id,
            project_id=aref['project_id'],
            artifact_ref=dict(aref),
            tags=list(self.tags))
        return d

class UserTags(MappedClass):
    class __mongometa__:
        session = main_orm_session
        name = 'user_tags'

    _id = FieldProperty(S.ObjectId)
    user_id = ForeignIdProperty('User')
    artifact_reference = FieldProperty(ArtifactReference)
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
