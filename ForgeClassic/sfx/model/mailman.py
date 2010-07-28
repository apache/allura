import json
from time import time
from datetime import datetime

import tg
from sqlalchemy import and_
from pylons import c as context
from pylons import g

from ming.utils import LazyProperty

from pyforge.lib import helpers as h
from .sfx_model import tables as T

common_suffix = tg.config.get('forgemail.domain', '.sourceforge.net')

class List(object):
    PUBLIC=1
    PRIVATE=0
    HIDDEN=9
    DELETE=2

    def __init__(self, name):
        self.name = name

    @classmethod
    def find(cls):
        q = T.mail_group_list.select()
        q = q.where(T.mail_group_list.c.group_id==context.project.get_tool_data('sfx', 'group_id'))
        for row in q.execute():
            lst = List(row['list_name'])
            lst._sitedb_row = row
            yield lst

    @LazyProperty
    def _sitedb_row(self):
        q = T.mail_group_list.select(T.mail_group_list.c.list_name==self.name)
        q = q.where(T.mail_group_list.c.group_id==context.project.get_tool_data('sfx', 'group_id'))
        return q.execute().first()

    @LazyProperty
    def _maildb_row(self):
        q = T.lists.select(T.lists.c.list_name==self.name)
        return q.execute().first()

    @property
    def group_id(self):
        return self._sitedb_row['group_id']

    @property
    def group_list_id(self):
        return self._sitedb_row['group_list_id']

    @property
    def description(self):
        return self._sitedb_row['description']

    @property
    def is_public(self):
        return self._sitedb_row['is_public']

    @property
    def admin_url(self):
        return 'https://lists.sourceforge.net/mailman/admin/%s' % self.name

    @property
    def subscribers_url(self):
        return g.url('/mail/admin/list_subscribers.php',
                     group_id=self.group_id,
                     group_list_id=self.group_list_id)

    @property
    def password_url(self):
        return g.url('/mail/admin/list_adminpass.php',
                     group_id=self.group_id,
                     group_list_id=self.group_list_id)

    def create(self, is_public, description):
        password = h.nonce(6)
        stmt = T.mail_group_list.insert()
        stmt = stmt.values(
            group_id=context.project.get_tool_data('sfx', 'group_id'),
            list_name=self.name,
            is_public=is_public,
            password=password,
            list_admin=context.user.get_tool_data('sfx', 'userid'),
            status=0,
            description=description)
        stmt.execute()
        tg.flash('Your new mailing list has been queued for creation.'
                 'Your list password is %s' % password)

    def update(self, is_public, description):
        if self.is_public == is_public and self.description == description:
            return
        stmt = T.mail_group_list.update(
            where=and_(
                T.mail_group_list.c.group_id==self.group_id,
                T.mail_group_list.c.group_list_id==self.group_list_id))
        stmt.execute(is_public=is_public, description=description)
        stmt = T.lists.update(where=T.lists.c.name==self.name)
        stmt.execute(is_public=is_public)
        tg.flash('The mailing list was successfully updated')

    def delete(self):
        operation_detail=json.dumps(dict(
                priority=50,
                force_service_type='ml',
                reason='Delete request via mail admin',
                list_name=self.name,
                old_name=context.project.get_tool_data('sfx', 'uniq_group_name')))
        stmt = T.backend_queue.insert()
        time_submitted=int(
            time.mktime(datetime.utcnow().utctimetuple()))
        stmt.execute(
            time_submitted=time_submitted,
            submitter_table='user',
            submitter_pk=context.user.get_tool_data('sfx', 'userid'),
            target_table='project',
            target_pk=self.group_id,
            operation_type='purge_remove',
            operation_detail=operation_detail,
            operation_status_type='pending',
            operation_status_detail='Purge remove ml pending')
