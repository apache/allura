# -*- coding: utf-8 -*-
import sys
import shutil
import unittest
from base64 import b64encode

import mock
from pylons import c, g
from datadiff.tools import assert_equal
from nose.tools import assert_in
from ming.orm import FieldProperty, Mapper

from alluratest.controller import setup_basic_test, setup_global_objects

from allura import model as M
from allura.lib import helpers as h
from allura.lib.exceptions import CompoundError
from allura.tasks import event_tasks
from allura.tasks import index_tasks
from allura.tasks import mail_tasks
from allura.tasks import notification_tasks
from allura.tasks import repo_tasks
from allura.tests import decorators as td
from allura.lib.decorators import event_handler, task

class TestEventTasks(unittest.TestCase):

    def setUp(self):
        self.called_with = []

    def test_fire_event(self):
        event_tasks.event('my_event', self, 1, 2, a=5)
        assert self.called_with == [((1,2), {'a':5}) ], self.called_with

    def test_compound_error(self):
        '''test_compound_exception -- make sure our multi-exception return works
        OK
        '''
        setup_basic_test()
        setup_global_objects()
        t = raise_exc.post()
        self.assertRaises(CompoundError, t)
        for x in range(10):
            assert ('assert %d' % x) in t.result

class TestIndexTasks(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        setup_global_objects()

    @td.with_wiki
    def test_add_artifacts(self):
        old_shortlinks = M.Shortlink.query.find().count()
        old_solr_size = len(g.solr.db)
        artifacts = [ _TestArtifact() for x in range(5) ]
        for i, a in enumerate(artifacts):
            a._shorthand_id = 't%d' % i
            a.text = 'This is a reference to [t3]'
        arefs = [ M.ArtifactReference.from_artifact(a) for a in artifacts ]
        ref_ids = [ r._id for r in arefs ]
        M.artifact_orm_session.flush()
        index_tasks.add_artifacts(ref_ids)
        new_shortlinks = M.Shortlink.query.find().count()
        new_solr_size = len(g.solr.db)
        assert old_shortlinks + 5 == new_shortlinks, 'Shortlinks not created'
        assert old_solr_size + 5 == new_solr_size, "Solr additions didn't happen"
        M.main_orm_session.flush()
        M.main_orm_session.clear()
        a = _TestArtifact.query.get(_shorthand_id='t3')
        assert len(a.backrefs) == 5, a.backrefs

    @td.with_wiki
    def test_del_artifacts(self):
        old_shortlinks = M.Shortlink.query.find().count()
        old_solr_size = len(g.solr.db)
        artifacts = [ _TestArtifact(_shorthand_id='ta_%s' % x) for x in range(5) ]
        M.artifact_orm_session.flush()
        arefs = [ M.ArtifactReference.from_artifact(a) for a in artifacts ]
        ref_ids = [ r._id for r in arefs ]
        M.artifact_orm_session.flush()
        index_tasks.add_artifacts(ref_ids)
        M.main_orm_session.flush()
        M.main_orm_session.clear()
        new_shortlinks = M.Shortlink.query.find().count()
        new_solr_size = len(g.solr.db)
        assert old_shortlinks + 5 == new_shortlinks, 'Shortlinks not created'
        assert old_solr_size + 5 == new_solr_size, "Solr additions didn't happen"
        index_tasks.del_artifacts(ref_ids)
        M.main_orm_session.flush()
        M.main_orm_session.clear()
        new_shortlinks = M.Shortlink.query.find().count()
        new_solr_size = len(g.solr.db)
        assert old_shortlinks == new_shortlinks, 'Shortlinks not deleted'
        assert old_solr_size == new_solr_size, "Solr deletions didn't happen"

class TestMailTasks(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        setup_global_objects()

    # these tests go down through the mail_util.SMTPClient.sendmail method
    # since usage is generally through the task, and not using mail_util directly

    def test_send_email_ascii_with_user_lookup(self):
        c.user = M.User.by_username('test-admin')
        with mock.patch.object(mail_tasks.smtp_client, '_client') as _client:
            mail_tasks.sendmail(
                fromaddr=str(c.user._id),
                destinations=[ str(c.user._id) ],
                text=u'This is a test',
                reply_to=u'noreply@sf.net',
                subject=u'Test subject',
                message_id=h.gen_message_id())
            assert_equal(_client.sendmail.call_count, 1)
            return_path, rcpts, body = _client.sendmail.call_args[0]
            body = body.split('\n')

            assert_equal(rcpts, [c.user.get_pref('email_address')])
            assert_in('Reply-To: noreply@sf.net', body)
            assert_in('From: "Test Admin" <test-admin@users.localhost>', body)
            assert_in('Subject: Test subject', body)
            # plain
            assert_in('This is a test', body)
            # html
            assert_in('<div class="markdown_content"><p>This is a test</p></div>', body)

    def test_send_email_nonascii(self):
        with mock.patch.object(mail_tasks.smtp_client, '_client') as _client:
            mail_tasks.sendmail(
                fromaddr=u'"По" <foo@bar.com>',
                destinations=[ 'blah@blah.com' ],
                text=u'Громады стройные теснятся',
                reply_to=u'noreply@sf.net',
                subject=u'По оживлённым берегам',
                message_id=h.gen_message_id())
            assert_equal(_client.sendmail.call_count, 1)
            return_path, rcpts, body = _client.sendmail.call_args[0]
            body = body.split('\n')

            assert_equal(rcpts, ['blah@blah.com'])
            assert_in('Reply-To: noreply@sf.net', body)

            # The address portion must not be encoded, only the name portion can be.
            # Also it is apparently not necessary to have the double-quote separators present
            #   when the name portion is encoded.  That is, the encoding below is just По and not "По"
            assert_in('From: =?utf-8?b?0J/Qvg==?= <foo@bar.com>', body)
            assert_in('Subject: =?utf-8?b?0J/QviDQvtC20LjQstC70ZHQvdC90YvQvCDQsdC10YDQtdCz0LDQvA==?=', body)
            assert_in('Content-Type: text/plain; charset="utf-8"', body)
            assert_in('Content-Transfer-Encoding: base64', body)
            assert_in(b64encode(u'Громады стройные теснятся'.encode('utf-8')), body)

    @td.with_wiki
    def test_receive_email_ok(self):
        c.user = M.User.by_username('test-admin')
        import forgewiki
        with mock.patch.object(forgewiki.wiki_main.ForgeWikiApp, 'handle_message') as f:
            mail_tasks.route_email(
                '0.0.0.0', c.user.email_addresses[0],
                ['Page@wiki.test.p.in.sf.net'],
                'This is a mail message')
            args, kwargs = f.call_args
            assert args[0] == 'Page'
            assert len(args) == 2

class TestNotificationTasks(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        setup_global_objects()

    def test_delivers_messages(self):
        with mock.patch.object(M.Mailbox, 'deliver') as deliver:
            with mock.patch.object(M.Mailbox, 'fire_ready') as fire_ready:
                notification_tasks.notify('42', '52', 'none')
                assert deliver.called_with('42', '52', 'none')
                assert fire_ready.called_with()

class TestRepoTasks(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        self.setup_with_tools()

    @td.with_svn
    def setup_with_tools(self):
        h.set_context('test', 'src', neighborhood='Projects')

    def test_init(self):
        ns = M.Notification.query.find().count()
        with mock.patch.object(c.app.repo, 'init') as f:
            repo_tasks.init()
            M.main_orm_session.flush()
            assert f.called_with()
            assert ns + 1 == M.Notification.query.find().count()

    def test_clone(self):
        ns = M.Notification.query.find().count()
        with mock.patch.object(c.app.repo, 'init_as_clone') as f:
            repo_tasks.clone('foo', 'bar', 'baz')
            M.main_orm_session.flush()
            f.assert_called_with('foo', 'bar', 'baz')
            assert ns + 1 == M.Notification.query.find().count()

    def test_refresh(self):
        with mock.patch.object(c.app.repo, 'refresh') as f:
            repo_tasks.refresh()
            f.assert_called_with()

    def test_uninstall(self):
        with mock.patch.object(shutil, 'rmtree') as f:
            repo_tasks.uninstall()
            f.assert_called_with('/tmp/svn/p/test/src', ignore_errors=True)

@event_handler('my_event')
def _my_event(event_type, testcase, *args, **kwargs):
    testcase.called_with.append((args, kwargs))

@task
def raise_exc():
    errs = []
    for x in range(10):
        try:
            assert False, 'assert %d' % x
        except:
            errs.append(sys.exc_info())
    raise CompoundError(*errs)

class _TestArtifact(M.Artifact):
    _shorthand_id = FieldProperty(str)
    text = FieldProperty(str)
    def url(self): return ''
    def shorthand_id(self):
        return getattr(self, '_shorthand_id', self._id)
    def index(self):
        return dict(
            super(_TestArtifact, self).index(),
            text=self.text)

Mapper.compile_all()
