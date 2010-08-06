import json
from time import time
from datetime import datetime

import tg
import sqlalchemy as sa
from pylons import c as context
from pylons import g

from ming.utils import LazyProperty

from pyforge.lib import helpers as h
from .sfx_model import tables as T

class List(object):
    PRIVATE=0
    PUBLIC=1
    DELETE=2
    HIDDEN=9

    def __init__(self, name):
        self.name = name

    @classmethod
    def find(cls):
        q = T.mail_group_list.select()
        q = q.where(
            T.mail_group_list.c.group_id==context.project.get_tool_data('sfx', 'group_id'))
        for row in q.execute():
            lst = List(row['list_name'])
            lst._sitedb_row = row
            yield lst

    @LazyProperty
    def _sitedb_row(self):
        q = T.mail_group_list.select(T.mail_group_list.c.list_name==self.name)
        q = q.where(
            T.mail_group_list.c.group_id==context.project.get_tool_data('sfx', 'group_id'))
        return q.execute().first()

    def __getattr__(self, name):
        try:
            return self._sitedb_row[name]
        except KeyError:
            raise AttributeError, name

    @property
    def admin_url(self):
        return 'https://lists.sourceforge.net/mailman/admin/%s' % self.name

    @classmethod
    def create(cls, name, is_public, description):
        name = name.lower().replace('/', '')
        # Copy checks from www/mail/admin/index.php
        short_names = ('svn', 'cvs', 'hg', 'bzr', 'git')
        if len(name) < 4 and name not in short_names:
            tg.flash('List name must contain at least 4 characters'
                     ' unless named one of %s' % ','.join(short_names),
                     'error')
            return None
        if not h.re_path_portion.match(name):
            tg.flash('List name must contain be alphanumeric (dashes permitted)'
                     ' and start with a letter',
                     'unless named one of %s' % ','.join(short_names),
                     'error')
            return None
        if name.endswith('admin'):
            tg.flash('List name cannot end in "admin".', 'error')
            return None

        # Omit PHP NameChecker code and validate_email code on the presumption
        # that our re_path_portion match above is sufficient

        # Omit select for existing mailing list; this should be handled by a
        # unique constraint on list_name in mail_group_list.  The check in the
        # php has a race condition anyway.

        password = h.nonce(6)
        stmt = T.mail_group_list.insert()
        stmt = stmt.values(
            group_id=context.project.get_tool_data('sfx', 'group_id'),
            list_name=name,
            is_public=is_public,
            password=password,
            list_admin=context.user.get_tool_data('sfx', 'userid'),
            status=0,
            description=description)
        try:
            stmt.execute()
        except Exception, ex:
            tg.flash('Error creating list: %s, %s' % (ex.__class__.__name__, ex))
            return None
        tg.flash('Your new mailing list has been queued for creation.'
                 'Your list password is %s' % password)
        return cls(name=name)

    def update(self, is_public, description):
        if self.is_public == is_public and self.description == description:
            return

        stmt = T.mail_group_list.update(
            where=sa.and_(
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

    def change_password(self, new_password):
        stmt = T.ml_password_change.insert()
        stmt.execute(
            ml_name=self.name,
            password=new_password)

    def subscribers(self, search_criteria=None, sort_by='user name', ):
        q = T.mllist_subscriber.select()
        q = q.where(T.mllist_subscriber.c.ml_list_name==self.name)
        if search_criteria is not None:
            q = q.where(T.mllist_subscriber.c.subscribed_email.ilike(search_criteria))
        if sort_by != 'user name':
            q = q.order_by(
                sa.text("substring(subscribed_email from '@.*') ASC"))
        q = q.order_by(T.mllist_subscriber.c.subscribed_email)
        return (Subscriber(row) for row in q.execute())

class Subscriber(object):

    def __init__(self, row):
        self._row = row

    def __getattr__(self, name):
        try:
            return self._row[name]
        except KeyError:
            raise AttributeError, name
