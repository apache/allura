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

import unittest
from datetime import timedelta
import collections

from tg import tmpl_context as c, app_globals as g
from ming.orm import ThreadLocalORMSession
import mock
import bson

from alluratest.controller import setup_basic_test, setup_global_objects
from allura import model as M
from allura.model.notification import MailFooter
from allura.lib import helpers as h
from allura.tests import decorators as td
from forgewiki import model as WM


class TestNotification(unittest.TestCase):

    def setup_method(self, method):
        setup_basic_test()
        self.setup_with_tools()

    @td.with_wiki
    def setup_with_tools(self):
        setup_global_objects()
        _clear_subscriptions()
        _clear_notifications()
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        M.notification.MAILBOX_QUIESCENT = None  # disable message combining

    def test_subscribe_unsubscribe(self):
        M.Mailbox.subscribe(type='direct')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        subscriptions = M.Mailbox.query.find(dict(
            project_id=c.project._id,
            app_config_id=c.app.config._id,
            user_id=c.user._id)).all()
        assert len(subscriptions) == 1
        assert subscriptions[0].type == 'direct'
        assert M.Mailbox.query.find().count() == 1
        M.Mailbox.unsubscribe()
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        subscriptions = M.Mailbox.query.find(dict(
            project_id=c.project._id,
            app_config_id=c.app.config._id,
            user_id=c.user._id)).all()
        assert len(subscriptions) == 0
        assert M.Mailbox.query.find().count() == 0

    @mock.patch('allura.tasks.mail_tasks.sendmail')
    def test_send_direct(self, sendmail):
        c.user = M.User.query.get(username='test-user')
        wiki = c.project.app_instance('wiki')
        page = WM.Page.query.get(app_config_id=wiki.config._id)
        notification = M.Notification(
            _id='_id',
            ref=page.ref,
            from_address='from_address',
            reply_to_address='reply_to_address',
            in_reply_to='in_reply_to',
            references=['a'],
            subject='subject',
            text='text',
        )
        notification.footer = lambda: ' footer'
        notification.send_direct(c.user._id)
        sendmail.post.assert_called_once_with(
            destinations=[str(c.user._id)],
            fromaddr='from_address',
            reply_to='reply_to_address',
            subject='subject',
            message_id='_id',
            in_reply_to='in_reply_to',
            references=['a'],
            sender='wiki@test.p.in.localhost',
            text='text footer',
            metalink=None,
        )

    @mock.patch('allura.tasks.mail_tasks.sendmail')
    def test_send_direct_no_access(self, sendmail):
        c.user = M.User.query.get(username='test-user')
        wiki = c.project.app_instance('wiki')
        page = WM.Page.query.get(app_config_id=wiki.config._id)
        page.parent_security_context().acl = []
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        notification = M.Notification(
            _id='_id',
            ref=page.ref,
            from_address='from_address',
            reply_to_address='reply_to_address',
            in_reply_to='in_reply_to',
            subject='subject',
            text='text',
        )
        notification.footer = lambda: ' footer'
        notification.send_direct(c.user._id)
        assert sendmail.post.call_count == 0

    @mock.patch('allura.tasks.mail_tasks.sendmail')
    def test_send_direct_wrong_project_context(self, sendmail):
        """
        Test that Notification.send_direct() works as expected even
        if c.project is wrong.

        This can happen when a notify task is triggered on project A (thus
        setting c.project to A) and then calls Mailbox.fire_ready() which fires
        pending Notifications on any waiting Mailbox, regardless of project,
        but doesn't update c.project.
        """
        project1 = c.project
        project2 = M.Project.query.get(shortname='test2')
        assert project1.shortname == 'test'
        c.user = M.User.query.get(username='test-user')
        wiki = project1.app_instance('wiki')
        page = WM.Page.query.get(app_config_id=wiki.config._id)
        notification = M.Notification(
            _id='_id',
            ref=page.ref,
            from_address='from_address',
            reply_to_address='reply_to_address',
            in_reply_to='in_reply_to',
            references=['a'],
            subject='subject',
            text='text',
        )
        notification.footer = lambda: ' footer'
        c.project = project2
        notification.send_direct(c.user._id)
        sendmail.post.assert_called_once_with(
            destinations=[str(c.user._id)],
            fromaddr='from_address',
            reply_to='reply_to_address',
            subject='subject',
            message_id='_id',
            in_reply_to='in_reply_to',
            references=['a'],
            sender='wiki@test.p.in.localhost',
            text='text footer',
            metalink=None,
        )


class TestPostNotifications(unittest.TestCase):

    def setup_method(self, method):
        setup_basic_test()
        self.setup_with_tools()

    @td.with_wiki
    def setup_with_tools(self):
        setup_global_objects()
        g.set_app('wiki')
        _clear_subscriptions()
        _clear_notifications()
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        self.pg = WM.Page.query.get(app_config_id=c.app.config._id)
        M.notification.MAILBOX_QUIESCENT = None  # disable message combining
        while M.MonQTask.run_ready('setup'):
            ThreadLocalORMSession.flush_all()

    def test_post_notification(self):
        self._post_notification()
        ThreadLocalORMSession.flush_all()
        M.MonQTask.list()
        t = M.MonQTask.get()
        assert t.args[1] == [self.pg.index_id()]

    def test_post_user_notification(self):
        u = M.User.query.get(username='test-admin')
        M.Notification.post_user(u, self.pg, 'metadata')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        flash_msgs = list(h.pop_user_notifications(u))
        assert len(flash_msgs) == 1, flash_msgs
        msg = flash_msgs[0]
        assert msg['text'].startswith('Home modified by Test Admin')
        assert msg['subject'].startswith('[test:wiki]')
        flash_msgs = list(h.pop_user_notifications(u))
        assert not flash_msgs, flash_msgs

    def test_delivery(self):
        self._subscribe()
        self._post_notification()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        assert M.Mailbox.query.find().count() == 1
        mbox = M.Mailbox.query.get()
        assert len(mbox.queue) == 1
        assert not mbox.queue_empty

    def test_email(self):
        self._subscribe()  # as current user: test-admin
        user2 = M.User.query.get(username='test-user-2')
        self._subscribe(user=user2)
        self._post_notification()
        ThreadLocalORMSession.flush_all()

        assert (M.Notification.query.get()
                     ['from_address'] == '"Test Admin" <test-admin@users.localhost>')
        assert M.Mailbox.query.find().count() == 2

        # sends the notification out into "mailboxes", and from mailboxes into
        # email tasks
        M.MonQTask.run_ready()
        mboxes = M.Mailbox.query.find().all()
        assert len(mboxes) == 2
        assert len(mboxes[0].queue) == 1
        assert not mboxes[0].queue_empty
        assert len(mboxes[1].queue) == 1
        assert not mboxes[1].queue_empty

        email_tasks = M.MonQTask.query.find({'state': 'ready'}).all()
        # make sure both subscribers will get an email
        assert len(email_tasks) == 2

        first_destinations = [e.kwargs['destinations'][0] for e in email_tasks]
        assert str(c.user._id) in first_destinations
        assert str(user2._id) in first_destinations
        assert (email_tasks[0].kwargs['fromaddr'] ==
                     '"Test Admin" <test-admin@users.localhost>')
        assert (email_tasks[1].kwargs['fromaddr'] ==
                     '"Test Admin" <test-admin@users.localhost>')
        assert (email_tasks[0].kwargs['sender'] ==
                     'wiki@test.p.in.localhost')
        assert (email_tasks[1].kwargs['sender'] ==
                     'wiki@test.p.in.localhost')
        assert email_tasks[0].kwargs['text'].startswith(
            'Home modified by Test Admin')
        assert 'you indicated interest in ' in email_tasks[0].kwargs['text']

    def test_permissions(self):
        # Notification should only be delivered if user has read perms on the
        # artifact. The perm check happens just before the mail task is
        # posted.
        u = M.User.query.get(username='test-admin')
        self._subscribe(user=u)
        # Simulate a permission check failure.

        def patched_has_access(*args, **kw):
            def predicate(*args, **kw):
                return False
            return predicate
        from allura.model.notification import security
        orig = security.has_access
        security.has_access = patched_has_access
        try:
            # this will create a notification task
            self._post_notification()
            ThreadLocalORMSession.flush_all()
            # running the notification task will create a mail task if the
            # permission check passes...
            M.MonQTask.run_ready()
            ThreadLocalORMSession.flush_all()
            # ...but in this case it doesn't create a mail task since we
            # forced the perm check to fail
            assert M.MonQTask.get() is None
        finally:
            security.has_access = orig

    def test_footer(self):
        footer = MailFooter.monitored(
            'test@mail.com',
            'http://test1.com',
            'http://test2.com')
        assert 'test@mail.com is subscribed to http://test1.com' in footer
        assert 'admin can change settings at http://test2.com' in footer
        footer = MailFooter.standard(M.Notification())
        self.assertIn('Sent from localhost because you indicated interest',
                      footer)

    def _subscribe(self, **kw):
        self.pg.subscribe(type='direct', **kw)
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def _post_notification(self):
        return M.Notification.post(self.pg, 'metadata')


class TestSubscriptionTypes(unittest.TestCase):

    def setup_method(self, method):
        setup_basic_test()
        self.setup_with_tools()

    @td.with_wiki
    def setup_with_tools(self):
        setup_global_objects()
        g.set_app('wiki')
        _clear_subscriptions()
        _clear_notifications()
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        self.pg = WM.Page.query.get(app_config_id=c.app.config._id)
        M.notification.MAILBOX_QUIESCENT = None  # disable message combining

    def test_direct_sub(self):
        self._subscribe()
        self._post_notification(text='A')
        self._post_notification(text='B')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        M.Mailbox.fire_ready()

    def test_digest_sub(self):
        self._subscribe(type='digest')
        self._post_notification(text='x' * 1024)
        self._post_notification()
        M.Mailbox.fire_ready()

    def test_summary_sub(self):
        self._subscribe(type='summary')
        self._post_notification(text='x' * 1024)
        self._post_notification()
        M.Mailbox.fire_ready()

    def test_message(self):
        self._test_message()

        self.setup_method(None)
        self._test_message()

        self.setup_method(None)
        M.notification.MAILBOX_QUIESCENT = timedelta(minutes=1)
        # will raise "assert msg is not None" since the new message is not 1
        # min old:
        self.assertRaises(AssertionError, self._test_message)

    def _test_message(self):
        self._subscribe()
        thd = M.Thread.query.get(ref_id=self.pg.index_id())
        thd.post('This is a very cool message')
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        M.Mailbox.fire_ready()
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        msg = M.MonQTask.query.get(
            task_name='allura.tasks.mail_tasks.sendmail',
            state='ready')
        assert msg is not None
        assert 'Home@wiki.test.p' in msg.kwargs['reply_to']
        u = M.User.by_username('test-admin')
        assert str(u._id) in msg.kwargs['fromaddr'], msg.kwargs['fromaddr']

    def _clear_subscriptions(self):
        M.Mailbox.query.remove({})
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def _subscribe(self, type='direct', topic=None):
        self.pg.subscribe(type=type, topic=topic)
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def _post_notification(self, text=None):
        return M.Notification.post(self.pg, 'metadata', text=text)

    @mock.patch('allura.model.notification.defaultdict')
    @mock.patch('allura.model.notification.Notification')
    def test_direct_accumulation(self, mocked_notification, mocked_defaultdict):
        class OrderedDefaultDict(collections.OrderedDict):

            def __init__(self, factory=list, *a, **kw):
                self._factory = factory
                super().__init__(*a, **kw)

            def __getitem__(self, key):
                if key not in self:
                    value = self[key] = self._factory()
                else:
                    value = super().__getitem__(key)
                return value

        notifications = mocked_notification.query.find.return_value.all.return_value = [
            mock.Mock(_id='n0', topic='metadata', subject='s1',
                      from_address='f1', reply_to_address='rt1', author_id='a1'),
            mock.Mock(_id='n1', topic='metadata', subject='s2',
                      from_address='f2', reply_to_address='rt2', author_id='a2'),
            mock.Mock(_id='n2', topic='metadata', subject='s2',
                      from_address='f2', reply_to_address='rt2', author_id='a2'),
            mock.Mock(_id='n3', topic='message', subject='s3',
                      from_address='f3', reply_to_address='rt3', author_id='a3'),
            mock.Mock(_id='n4', topic='message', subject='s3',
                      from_address='f3', reply_to_address='rt3', author_id='a3'),
        ]
        mocked_defaultdict.side_effect = OrderedDefaultDict

        u0 = bson.ObjectId()
        mbox = M.Mailbox(type='direct', user_id=u0,
                         queue=['n0', 'n1', 'n2', 'n3', 'n4'])
        mbox.fire('now')

        mocked_notification.query.find.assert_called_once_with(
            {'_id': {'$in': ['n0', 'n1', 'n2', 'n3', 'n4']}})
        # first notification should be sent direct, as its key values are
        # unique
        notifications[0].send_direct.assert_called_once_with(u0)
        # next two notifications should be sent as a digest as they have
        # matching key values
        mocked_notification.send_digest.assert_called_once_with(
            u0, 'f2', 's2', [notifications[1], notifications[2]], 'rt2')
        # final two should be sent direct even though they matching keys, as
        # they are messages
        notifications[3].send_direct.assert_called_once_with(u0)
        notifications[4].send_direct.assert_called_once_with(u0)

    def test_send_direct_disabled_user(self):
        user = M.User.by_username('test-admin')
        thd = M.Thread.query.get(ref_id=self.pg.index_id())
        notification = M.Notification()
        notification.ref_id = thd.index_id()
        user.disabled = True
        ThreadLocalORMSession.flush_all()
        notification.send_direct(user._id)
        count = M.MonQTask.query.find(dict(
            task_name='allura.tasks.mail_tasks.sendmail',
            state='ready')).count()
        assert count == 0
        user.disabled = False
        ThreadLocalORMSession.flush_all()
        notification.send_direct(user._id)
        count = M.MonQTask.query.find(dict(
            task_name='allura.tasks.mail_tasks.sendmail',
            state='ready')).count()
        assert count == 1

    @mock.patch('allura.model.notification.Notification.ref')
    def test_send_digest_disabled_user(self, ref):
        thd = M.Thread.query.get(ref_id=self.pg.index_id())
        notification = M.Notification()
        notification.ref_id = thd.index_id()
        ref.artifact = thd
        user = M.User.by_username('test-admin')
        user.disabled = True
        ThreadLocalORMSession.flush_all()
        M.Notification.send_digest(
            user._id, 'test@mail.com', 'subject', [notification])
        count = M.MonQTask.query.find(dict(
            task_name='allura.tasks.mail_tasks.sendmail',
            state='ready')).count()
        assert count == 0
        user.disabled = False
        ThreadLocalORMSession.flush_all()
        M.Notification.send_digest(
            user._id, 'test@mail.com', 'subject', [notification])
        count = M.MonQTask.query.find(dict(
            task_name='allura.tasks.mail_tasks.sendmail',
            state='ready')).count()
        assert count == 1


class TestSiteNotification(unittest.TestCase):
    def setup_method(self, method):
        self.note = M.SiteNotification(
            active=True,
            impressions=0,
            content='test',
            page_regex='',
            page_tool_type='',
            user_role=''
        )

    def test_json_type(self):
        note_json = self.note.__json__()
        assert isinstance(note_json, dict)

    def test_json_keys(self):
        keys = list(self.note.__json__().keys())
        assert 'active' in keys
        assert 'impressions' in keys
        assert 'content' in keys
        assert 'page_regex' in keys
        assert 'page_tool_type' in keys
        assert 'user_role' in keys

    def test_json_values_if_missing(self):
        note_json = self.note.__json__()
        assert note_json['page_regex'] == ''
        assert note_json['page_tool_type'] == ''
        assert note_json['user_role'] == ''


def _clear_subscriptions():
    M.Mailbox.query.remove({})


def _clear_notifications():
    M.Notification.query.remove({})
