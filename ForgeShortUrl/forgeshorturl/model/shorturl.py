from ming.orm.declarative import MappedClass
from allura.model import project_orm_session
from ming.orm import FieldProperty, ForeignIdProperty
from datetime import datetime
from ming import schema
from allura.model.auth import User
from allura.model import Project
from allura.model.timeline import ActivityNode, ActivityObject


class ShortUrl(MappedClass, ActivityNode, ActivityObject):

    class __mongometa__:
        name = 'short_urs'
        session = project_orm_session
        indexes = ['short_name']

    _id = FieldProperty(schema.ObjectId)
    url = FieldProperty(str)
    short_name = FieldProperty(str)
    description = FieldProperty(str)
    private = FieldProperty(bool)
    create_user = ForeignIdProperty(User)
    created = FieldProperty(datetime, if_missing=datetime.utcnow)
    last_updated = FieldProperty(datetime, if_missing=datetime.utcnow)
    project_id = ForeignIdProperty(Project)

    @property
    def user(self):
        return User.query.get(_id=self.create_user)
