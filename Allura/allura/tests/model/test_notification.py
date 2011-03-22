import unittest
from datetime import timedelta

from pylons import g, c

from ming.orm import ThreadLocalORMSession

from alluratest.controller import setup_basic_test, setup_global_objects, REGISTRY
from allura import model as M
from allura.lib import helpers as h
from forgewiki import model as WM

class TestNotification(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        setup_global_objects()
        _clear_subscriptions()
        _clear_notifications()
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        M.notification.MAILBOX_QUIESCENT=None # disable message combining

    def test_subscribe_unsubscribe(self):
        M.Mailbox.subscribe(type='direct')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        subscriptions = M.Mailbox.query.find(dict(
            project_id=c.project._id,
            app_config_id=c.app.config._id,
            user_id=c.user._id)).all()
        assert len(subscriptions) == 1
        assert subscriptions[0].type=='direct'
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

class TestPostNotifications(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        setup_global_objects()
        g.set_app('wiki')
        _clear_subscriptions()
        _clear_notifications()
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        self.pg = WM.Page.query.get(app_config_id=c.app.config._id)
        M.notification.MAILBOX_QUIESCENT=None # disable message combining
        while M.MonQTask.run_ready('setup'):
            ThreadLocalORMSession.flush_all()

    def test_post_notification(self):
        self._post_notification()
        ThreadLocalORMSession.flush_all()
        M.MonQTask.list()
        t = M.MonQTask.get()
        assert t.args[1] == self.pg.index_id()

    def test_post_user_notification(self):
        u = M.User.query.get(username='test-admin')
        n = M.Notification.post_user(u, self.pg, 'metadata')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        flash_msgs = list(h.pop_user_notifications(u))
        assert len(flash_msgs) == 1, flash_msgs
        msg = flash_msgs[0]
        assert msg['text'].startswith('WikiPage Home modified by Test Admin')
        assert msg['subject'].startswith('[test:wiki]')
        flash_msgs = list(h.pop_user_notifications(u))
        assert not flash_msgs, flash_msgs

    def test_delivery(self):
        self._subscribe()
        self._post_notification()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        assert M.Mailbox.query.find().count()==1
        mbox = M.Mailbox.query.get()
        assert len(mbox.queue) == 1

    def test_email(self):
        self._subscribe()
        self._post_notification()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        assert M.Notification.query.get()['from_address'].startswith('"Test Admin" <Beta')
        assert M.Mailbox.query.find().count()==1
        mbox = M.Mailbox.query.get()
        assert len(mbox.queue) == 1
        M.Mailbox.fire_ready()
        task = M.MonQTask.get()
        for addr in c.user.email_addresses:
            if addr in task.kwargs['fromaddr']: break
        else:
            assert False, 'From address is wrong: %s' % task.kwargs['fromaddr']
        assert task.kwargs['text'].startswith('WikiPage Home modified by Test Admin')
        assert 'you indicated interest in ' in task.kwargs['text']

    def _subscribe(self):
        self.pg.subscribe(type='direct')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def _post_notification(self):
        return M.Notification.post(self.pg, 'metadata')

class TestSubscriptionTypes(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        setup_global_objects()
        g.set_app('wiki')
        _clear_subscriptions()
        _clear_notifications()
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        self.pg = WM.Page.query.get(app_config_id=c.app.config._id)
        M.notification.MAILBOX_QUIESCENT=None # disable message combining

    def test_direct_sub(self):
        self._subscribe()
        self._post_notification(text='A')
        self._post_notification(text='B')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        M.Mailbox.fire_ready()

    def test_digest_sub(self):
        self._subscribe(type='digest')
        self._post_notification(text='x'*1024)
        self._post_notification()
        M.Mailbox.fire_ready()

    def test_summary_sub(self):
        self._subscribe(type='summary')
        self._post_notification(text='x'*1024)
        self._post_notification()
        M.Mailbox.fire_ready()

    def test_message(self):
        self._test_message()
        self.setUp()
        self._test_message()
        self.setUp()
        M.notification.MAILBOX_QUIESCENT=timedelta(minutes=1)
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

def _clear_subscriptions():
        M.Mailbox.query.remove({})

def _clear_notifications():
        M.Notification.query.remove({})

