from time import sleep
from datetime import datetime

import tg
from pylons import g #g is a namespace for globally accessable app helpers
from pylons import c as context
from pylons import request

from pymongo.errors import OperationFailure

from ming import schema
from ming.orm.base import state, session
from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty, ForeignIdProperty, RelationProperty

from pyforge.model import Artifact
from pyforge.model import Notification, project_orm_session
from pyforge.lib import helpers as h

common_suffix = tg.config.get('forgemail.domain', '.sourceforge.net')

class List(Artifact):
    class __mongometa__:
        name = 'mailman-list'
        unique_indexes = [ ('name') ]

    type_s = 'Mailman List'
    _id = FieldProperty(schema.ObjectId)
    list_id = FieldProperty(int)
    name = FieldProperty(str)
    description = FieldProperty(str)
    visibility =FieldProperty(schema.OneOf('public', 'private', 'hidden',))

    @property
    def admin_url(self):
        return 'https://lists.sourceforge.net/mailman/admin/%s' % self.name

    @property
    def subscribers_url(self):
        return tg.url('https://sourceforge.net/mail/admin/list_subscribers.php',
                      dict(group_id=self.project.get_tool_data('sfx', 'group_id'),
                           group_list_id=self.list_id))

    @property
    def password_url(self):
        return tg.url('https://sourceforge.net/mail/admin/list_adminpass.php',
                      dict(group_id=self.project.get_tool_data('sfx', 'group_id'),
                           group_list_id=self.list_id))


MappedClass.compile_all()
