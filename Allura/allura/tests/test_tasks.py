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

import operator
import shutil
from textwrap import dedent
import unittest

import six
from base64 import b64encode
import logging
import pkg_resources

import tg
import mock
from tg import tmpl_context as c, app_globals as g

from ming.orm import FieldProperty, Mapper
from ming.orm import ThreadLocalORMSession
from testfixtures import LogCapture

from alluratest.controller import setup_basic_test, setup_global_objects, TestController

from allura import model as M
from allura.command.taskd import TaskdCommand
from allura.lib import helpers as h
from allura.lib.mail_util import MAX_MAIL_LINE_OCTETS
from allura.tasks import event_tasks
from allura.tasks import index_tasks
from allura.tasks import mail_tasks
from allura.tasks import notification_tasks
from allura.tasks import repo_tasks
from allura.tasks import export_tasks
from allura.tasks import admin_tasks
from allura.tests import decorators as td
from allura.tests.exclude_from_rewrite_hook import raise_compound_exception
from allura.lib.decorators import event_handler, task


class TestRepoTasks(unittest.TestCase):

    def setup_method(self, method):
        setup_basic_test()
        setup_global_objects()

    @mock.patch('allura.tasks.repo_tasks.c.app')
    @mock.patch('allura.tasks.repo_tasks.g.post_event')
    def test_clone_posts_event_on_failure(self, post_event, app):
        fake_source_url = 'fake_source_url'
        fake_traceback = 'fake_traceback'
        app.repo.init_as_clone.side_effect = Exception(fake_traceback)
        repo_tasks.clone(None, None, fake_source_url)
        assert post_event.call_args[0][0] == 'repo_clone_task_failed'
        assert post_event.call_args[0][1] == fake_source_url
        assert post_event.call_args[0][2] is None
        # ignore args[3] which is a traceback string

    @mock.patch('allura.tasks.repo_tasks.session', autospec=True)
    @mock.patch.object(M, 'MergeRequest')
    def test_merge(self, MR, session):
        mr = mock.Mock(_id='_id', activity_name='merge req', activity_url='/fake/url', activity_extras={}, node_id=None,
                       app=mock.Mock(activity_name='code merge', activity_url='/fake/url', activity_extras={}, node_id=None))
        MR.query.get.return_value = mr
        repo_tasks.merge(mr._id)
        mr.app.repo.merge.assert_called_once_with(mr)
        assert mr.status == 'merged'
        session.assert_called_once_with(mr)
        session.return_value.flush.assert_called_once_with(mr)

    @mock.patch.object(M, 'MergeRequest')
    def test_can_merge(self, MR):
        mr = M.MergeRequest(_id='_id')
        MR.query.get.return_value = mr
        repo_tasks.can_merge(mr._id)
        mr.app.repo.can_merge.assert_called_once_with(mr)
        val = mr.app.repo.can_merge.return_value
        mr.set_can_merge_cache.assert_called_once_with(val)


# used in test_post_event_from_within_task below
@task
def _task_that_creates_event(event_name,):
    g.post_event(event_name)
    # event does not get flushed to db right away (at end of task, ming middleware will flush it)
    assert not M.MonQTask.query.get(task_name='allura.tasks.event_tasks.event', args=[event_name])


class TestEventTasks(unittest.TestCase):

    def setup_method(self, method):
        setup_basic_test()
        setup_global_objects()
        self.called_with = []

    def test_fire_event(self):
        event_tasks.event('my_event', self, 1, 2, a=5)
        assert self.called_with == [((1, 2), {'a': 5})], self.called_with

    def test_post_event_explicit_flush(self):
        g.post_event('my_event1', flush_immediately=True)
        assert M.MonQTask.query.get(task_name='allura.tasks.event_tasks.event', args=['my_event1'])

        g.post_event('my_event2', flush_immediately=False)
        assert not M.MonQTask.query.get(task_name='allura.tasks.event_tasks.event', args=['my_event2'])
        ThreadLocalORMSession.flush_all()
        assert M.MonQTask.query.get(task_name='allura.tasks.event_tasks.event', args=['my_event2'])

    def test_post_event_from_script(self):
        # simulate post_event being called from a paster script command:
        with mock.patch.dict(tg.request.environ, PATH_INFO='--script--'):
            g.post_event('my_event3')
            # event task is flushed to db right away:
            assert M.MonQTask.query.get(task_name='allura.tasks.event_tasks.event', args=['my_event3'])

    def test_post_event_from_within_task(self):
        # instead of M.MonQTask.run_ready() run real 'taskd' so we get all the setup we need
        taskd = TaskdCommand('taskd')
        taskd.parse_args([pkg_resources.resource_filename('allura', '../test.ini')])
        taskd.keep_running = True
        taskd.restart_when_done = False
        _task_that_creates_event.post('my_event4')
        with mock.patch('allura.command.taskd.setproctitle') as setproctitle:
            def stop_taskd_after_this_task(*args):
                taskd.keep_running = False
            setproctitle.side_effect = stop_taskd_after_this_task  # avoid proc title change; useful hook to stop taskd
            taskd.worker()
        # after the initial task is done, the event task has been persisted:
        assert M.MonQTask.query.get(task_name='allura.tasks.event_tasks.event', args=['my_event4'])

    def test_compound_error(self):
        t = raise_compound_exception.post()
        with LogCapture(level=logging.ERROR) as l, \
                mock.patch.dict(tg.config, {'monq.raise_errors': False}):  # match normal non-test behavior
            t()
        # l.check() would be nice, but string is too detailed to check
        assert l.records[0].name == 'allura.model.monq_model'
        msg = l.records[0].getMessage()
        assert "AssertionError('assert 0'" in msg
        assert "AssertionError('assert 5'" in msg
        assert ' on job <MonQTask ' in msg
        assert ' (error) P:10 allura.tests.exclude_from_rewrite_hook.raise_compound_exception ' in msg
        for x in range(10):
            assert ('assert %d' % x) in t.result


class TestIndexTasks(unittest.TestCase):

    def setup_method(self, method):
        setup_basic_test()
        setup_global_objects()

    def test_add_projects(self):
        g.solr.db.clear()
        old_solr_size = len(g.solr.db)
        projects = M.Project.query.find().all()
        index_tasks.add_projects.post([p._id for p in projects])
        M.MonQTask.run_ready()
        new_solr_size = len(g.solr.db)
        assert old_solr_size + len(projects) == new_solr_size

    @td.with_wiki
    def test_del_projects(self):
        projects = M.Project.query.find().all()
        index_tasks.add_projects([p._id for p in projects])

        with mock.patch('allura.tasks.index_tasks.g.solr') as solr:
            index_tasks.del_projects([p.index_id() for p in projects])
            assert solr.delete.call_count, 1
            for project in projects:
                assert project.index_id() in solr.delete.call_args[1]['q']

    @td.with_wiki
    def test_add_artifacts(self):
        from allura.lib.search import find_shortlinks
        with mock.patch('allura.lib.search.find_shortlinks') as find_slinks:
            find_slinks.side_effect = lambda s: find_shortlinks(s)

            old_shortlinks = M.Shortlink.query.find().count()
            old_solr_size = len(g.solr.db)
            artifacts = [_TestArtifact() for x in range(5)]
            for i, a in enumerate(artifacts):
                a._shorthand_id = 't%d' % i
                a.text = 'This is a reference to [t3]'
            arefs = [M.ArtifactReference.from_artifact(a) for a in artifacts]
            ref_ids = [r._id for r in arefs]
            M.artifact_orm_session.flush()
            index_tasks.add_artifacts(ref_ids)
            new_shortlinks = M.Shortlink.query.find().count()
            new_solr_size = len(g.solr.db)
            assert old_shortlinks + \
                5 == new_shortlinks, 'Shortlinks not created'
            assert old_solr_size + \
                5 == new_solr_size, "Solr additions didn't happen"
            M.main_orm_session.flush()
            M.main_orm_session.clear()
            t3 = _TestArtifact.query.get(_shorthand_id='t3')
            assert len(t3.backrefs) == 5, t3.backrefs
            assert (find_slinks.call_args_list ==
                         [mock.call(a.index().get('text')) for a in artifacts])

    @td.with_wiki
    @mock.patch('allura.tasks.index_tasks.g.solr')
    def test_del_artifacts(self, solr):
        old_shortlinks = M.Shortlink.query.find().count()
        artifacts = [_TestArtifact(_shorthand_id='ta_%s' % x)
                     for x in range(5)]
        M.artifact_orm_session.flush()
        arefs = [M.ArtifactReference.from_artifact(a) for a in artifacts]
        ref_ids = [r._id for r in arefs]
        M.artifact_orm_session.flush()
        index_tasks.add_artifacts(ref_ids)
        M.main_orm_session.flush()
        M.main_orm_session.clear()
        new_shortlinks = M.Shortlink.query.find().count()
        assert old_shortlinks + 5 == new_shortlinks, 'Shortlinks not created'
        assert solr.add.call_count == 1
        sort_key = operator.itemgetter('id')
        assert (
            sorted(solr.add.call_args[0][0], key=sort_key) ==
            sorted((ref.artifact.solarize() for ref in arefs),
                   key=sort_key))
        index_tasks.del_artifacts(ref_ids)
        M.main_orm_session.flush()
        M.main_orm_session.clear()
        new_shortlinks = M.Shortlink.query.find().count()
        assert old_shortlinks == new_shortlinks, 'Shortlinks not deleted'
        solr_query = 'id:({})'.format(' || '.join(ref_ids))
        solr.delete.assert_called_once_with(q=solr_query)


class TestMailTasks(unittest.TestCase):

    def setup_method(self, method):
        setup_basic_test()
        setup_global_objects()

    # these tests go down through the mail_util.SMTPClient.sendmail method
    # since usage is generally through the task, and not using mail_util
    # directly

    def test_send_email_ascii_with_user_lookup(self):
        c.user = M.User.by_username('test-admin')
        with mock.patch.object(mail_tasks.smtp_client, '_client') as _client:
            mail_tasks.sendmail(
                fromaddr=str(c.user._id),
                destinations=[str(c.user._id)],
                text='This is a test',
                reply_to=g.noreply,
                subject='Test subject',
                message_id=h.gen_message_id())
            assert _client.sendmail.call_count == 1
            return_path, rcpts, body = _client.sendmail.call_args[0]
            body = body.split('\n')

            assert rcpts == [c.user.get_pref('email_address')]
            assert 'Reply-To: %s' % g.noreply in body
            assert 'From: "Test Admin" <test-admin@users.localhost>' in body
            assert 'Subject: Test subject' in body
            # plain
            assert 'This is a test' in body
            # html
            assert (
                '<div class="markdown_content"><p>This is a test</p></div>' in body)

    def test_send_email_nonascii(self):
        with mock.patch.object(mail_tasks.smtp_client, '_client') as _client:
            mail_tasks.sendmail(
                fromaddr='"По" <foo@bar.com>',
                destinations=['blah@blah.com'],
                text='Громады стройные теснятся',
                reply_to=g.noreply,
                subject='По оживлённым берегам',
                message_id=h.gen_message_id())
            assert _client.sendmail.call_count == 1
            return_path, rcpts, body = _client.sendmail.call_args[0]
            body = body.split('\n')

            assert rcpts == ['blah@blah.com']
            assert 'Reply-To: %s' % g.noreply in body

            # The address portion must not be encoded, only the name portion can be.
            # Also py2 and py3 vary in handling of double-quote separators when the name portion is encoded
            unquoted_cyrillic_No = '=?utf-8?b?0J/Qvg==?='  # По
            quoted_cyrillic_No = '=?utf-8?b?ItCf0L4i?='  # "По"
            assert (f'From: {quoted_cyrillic_No} <foo@bar.com>' in body or
                    f'From: {unquoted_cyrillic_No} <foo@bar.com>' in body), body
            assert (
                'Subject: =?utf-8?b?0J/QviDQvtC20LjQstC70ZHQvdC90YvQvCDQsdC10YDQtdCz0LDQvA==?=' in body)
            assert 'Content-Type: text/plain; charset="utf-8"' in body
            assert 'Content-Transfer-Encoding: base64' in body
            assert six.ensure_text(b64encode('Громады стройные теснятся'.encode())) in body

    def test_send_email_with_disabled_user(self):
        c.user = M.User.by_username('test-admin')
        c.user.disabled = True
        destination_user = M.User.by_username('test-user-1')
        destination_user.preferences['email_address'] = 'user1@mail.com'
        ThreadLocalORMSession.flush_all()
        with mock.patch.object(mail_tasks.smtp_client, '_client') as _client:
            mail_tasks.sendmail(
                fromaddr=str(c.user._id),
                destinations=[str(destination_user._id)],
                text='This is a test',
                reply_to=g.noreply,
                subject='Test subject',
                message_id=h.gen_message_id())
            assert _client.sendmail.call_count == 1
            return_path, rcpts, body = _client.sendmail.call_args[0]
            body = body.split('\n')
            assert 'From: %s' % g.noreply in body

    def test_send_email_with_disabled_destination_user(self):
        c.user = M.User.by_username('test-admin')
        destination_user = M.User.by_username('test-user-1')
        destination_user.preferences['email_address'] = 'user1@mail.com'
        destination_user.disabled = True
        ThreadLocalORMSession.flush_all()
        with mock.patch.object(mail_tasks.smtp_client, '_client') as _client:
            mail_tasks.sendmail(
                fromaddr=str(c.user._id),
                destinations=[str(destination_user._id)],
                text='This is a test',
                reply_to=g.noreply,
                subject='Test subject',
                message_id=h.gen_message_id())
            assert _client.sendmail.call_count == 0

    def test_sendsimplemail_with_disabled_user(self):
        c.user = M.User.by_username('test-admin')
        with mock.patch.object(mail_tasks.smtp_client, '_client') as _client:
            mail_tasks.sendsimplemail(
                fromaddr=str(c.user._id),
                toaddr='test@mail.com',
                text='This is a test',
                reply_to=g.noreply,
                subject='Test subject',
                message_id=h.gen_message_id())
            assert _client.sendmail.call_count == 1
            return_path, rcpts, body = _client.sendmail.call_args[0]
            body = body.split('\n')
            assert 'From: "Test Admin" <test-admin@users.localhost>' in body

            c.user.disabled = True
            ThreadLocalORMSession.flush_all()
            mail_tasks.sendsimplemail(
                fromaddr=str(c.user._id),
                toaddr='test@mail.com',
                text='This is a test',
                reply_to=g.noreply,
                subject='Test subject',
                message_id=h.gen_message_id())
            assert _client.sendmail.call_count == 2
            return_path, rcpts, body = _client.sendmail.call_args[0]
            body = body.split('\n')
            assert 'From: %s' % g.noreply in body

    def test_email_sender_to_headers(self):
        c.user = M.User.by_username('test-admin')
        with mock.patch.object(mail_tasks.smtp_client, '_client') as _client:
            mail_tasks.sendsimplemail(
                fromaddr=str(c.user._id),
                toaddr='test@mail.com',
                text='This is a test',
                reply_to=g.noreply,
                subject='Test subject',
                sender='tickets@test.p.domain.net',
                message_id=h.gen_message_id())
            assert _client.sendmail.call_count == 1
            return_path, rcpts, body = _client.sendmail.call_args[0]
            body = body.split('\n')
            assert 'From: "Test Admin" <test-admin@users.localhost>' in body
            assert 'Sender: tickets@test.p.domain.net' in body
            assert 'To: test@mail.com' in body

            _client.reset_mock()
            mail_tasks.sendmail(
                fromaddr=str(c.user._id),
                destinations=[str(c.user._id)],
                text='This is a test',
                reply_to='123@tickets.test.p.domain.net',
                subject='Test subject',
                sender='tickets@test.p.domain.net',
                message_id=h.gen_message_id())
            assert _client.sendmail.call_count == 1
            return_path, rcpts, body = _client.sendmail.call_args[0]
            body = body.split('\n')
            assert 'From: "Test Admin" <test-admin@users.localhost>' in body
            assert 'Sender: tickets@test.p.domain.net' in body
            assert 'To: 123@tickets.test.p.domain.net' in body

    def test_email_references_header(self):
        c.user = M.User.by_username('test-admin')
        with mock.patch.object(mail_tasks.smtp_client, '_client') as _client:
            mail_tasks.sendsimplemail(
                fromaddr=str(c.user._id),
                toaddr='test@mail.com',
                text='This is a test',
                reply_to=g.noreply,
                subject='Test subject',
                references=['a', 'b', 'c'],
                message_id=h.gen_message_id())
            assert _client.sendmail.call_count == 1
            return_path, rcpts, body = _client.sendmail.call_args[0]
            body = body.split('\n')
            assert 'From: "Test Admin" <test-admin@users.localhost>' in body
            assert 'References: <a> <b> <c>' in body

            _client.reset_mock()
            mail_tasks.sendmail(
                fromaddr=str(c.user._id),
                destinations=[str(c.user._id)],
                text='This is a test',
                reply_to=g.noreply,
                subject='Test subject',
                references='ref',
                message_id=h.gen_message_id())
            assert _client.sendmail.call_count == 1
            return_path, rcpts, body = _client.sendmail.call_args[0]
            body = body.split('\n')
            assert 'From: "Test Admin" <test-admin@users.localhost>' in body
            assert 'References: <ref>' in body

    def test_cc(self):
        c.user = M.User.by_username('test-admin')
        with mock.patch.object(mail_tasks.smtp_client, '_client') as _client:
            mail_tasks.sendsimplemail(
                fromaddr=str(c.user._id),
                toaddr='test@mail.com',
                text='This is a test',
                reply_to=g.noreply,
                subject='Test subject',
                cc='someone@example.com',
                message_id=h.gen_message_id())
            assert _client.sendmail.call_count == 1
            return_path, rcpts, body = _client.sendmail.call_args[0]
            assert 'CC: someone@example.com' in body
            assert 'someone@example.com' in rcpts

    def test_fromaddr_objectid_not_str(self):
        c.user = M.User.by_username('test-admin')
        with mock.patch.object(mail_tasks.smtp_client, '_client') as _client:
            mail_tasks.sendsimplemail(
                fromaddr=c.user._id,
                toaddr='test@mail.com',
                text='This is a test',
                reply_to=g.noreply,
                subject='Test subject',
                message_id=h.gen_message_id())
            assert _client.sendmail.call_count == 1
            return_path, rcpts, body = _client.sendmail.call_args[0]
            assert 'From: "Test Admin" <test-admin@users.localhost>' in body

    def test_send_email_long_lines_use_quoted_printable(self):
        with mock.patch.object(mail_tasks.smtp_client, '_client') as _client:
            mail_tasks.sendsimplemail(
                fromaddr='"По" <foo@bar.com>',
                toaddr='blah@blah.com',
                text=('0123456789' * 100) + '\n\n' + ('Громады стро ' * 100),
                reply_to=g.noreply,
                subject='По оживлённым берегам',
                references=['foo@example.com'] * 100,  # needs to handle really long headers as well
                message_id=h.gen_message_id())
            return_path, rcpts, body = _client.sendmail.call_args[0]
            body = body.split('\n')

            for line in body:
                assert len(line) <= MAX_MAIL_LINE_OCTETS

            # plain text
            assert '012345678901234567890123456789012345678901234567890123456789012345678901234=' in body
            assert '=D0=93=D1=80=D0=BE=D0=BC=D0=B0=D0=B4=D1=8B =D1=81=D1=82=D1=80=D0=BE =D0=93=' in body
            # html
            assert '<div class=3D"markdown_content"><p>0123456789012345678901234567890123456789=' in body
            assert '<p>=D0=93=D1=80=D0=BE=D0=BC=D0=B0=D0=B4=D1=8B =D1=81=D1=82=D1=80=D0=BE =D0=' in body

    @td.with_wiki
    def test_receive_email_ok(self):
        c.user = M.User.by_username('test-admin')
        import forgewiki
        with mock.patch.object(forgewiki.wiki_main.ForgeWikiApp, 'handle_message') as f:
            mail_tasks.route_email(
                '0.0.0.0', c.user.email_addresses[0],
                ['Page@wiki.test.p.in.localhost'],
                'This is a mail message')
            args, kwargs = f.call_args
            assert args[0] == 'Page'
            assert len(args) == 2

    @td.with_tool('test', 'Tickets', 'bugs')
    def test_receive_autoresponse(self):
        message = dedent('''\
            Date: Wed, 30 Oct 2013 01:38:40 -0700
            From: <test-admin@domain.net>
            To: <1@bugs.test.p.in.localhost>
            Message-ID: <super-unique-id>
            Subject: Not here Re: Message notification
            Precedence: bulk
            X-Autoreply: yes
            Auto-Submitted: auto-replied

            I'm not here''')
        import forgetracker
        c.user = M.User.by_username('test-admin')
        with mock.patch.object(forgetracker.tracker_main.ForgeTrackerApp, 'handle_message') as hm:
            mail_tasks.route_email(
                '0.0.0.0',
                c.user.email_addresses[0],
                ['1@bugs.test.p.in.localhost'],
                message)
            assert hm.call_count == 0

    @td.with_tool('test', 'Tickets', 'bugs')
    def test_email_posting_disabled(self):
        message = 'Hello, world!'
        import forgetracker
        c.user = M.User.by_username('test-admin')
        with mock.patch.object(forgetracker.tracker_main.ForgeTrackerApp, 'handle_message') as hm:
            c.app.config.options = {'AllowEmailPosting': False}
            mail_tasks.route_email(
                '0.0.0.0',
                c.user.email_addresses[0],
                ['1@bugs.test.p.in.localhost'],
                message)
            assert hm.call_count == 0


class TestUserNotificationTasks(TestController):
    def setup_method(self, method):
        super().setup_method(method)
        self.setup_with_tools()

    @td.with_wiki
    def setup_with_tools(self):
        pass

    def test_send_usermentions_notification(self):
        c.user = M.User.by_username('test-admin')
        test_user = M.User.by_username('test-user-1')
        test_user.set_pref('mention_notifications', True)
        M.MonQTask.query.remove()
        d = dict(title='foo', text='Hey @test-user-1!')
        self.app.post('/wiki/foo/update', params=d)
        M.MonQTask.run_ready()
        # check email notification
        tasks = M.MonQTask.query.find(
            dict(task_name='allura.tasks.mail_tasks.sendsimplemail')).all()
        assert len(tasks) == 1
        assert (tasks[0].kwargs['subject'] ==
                     '[test:wiki] Your name was mentioned')
        assert tasks[0].kwargs['toaddr'] == 'test-user-1@allura.local'
        assert tasks[0].kwargs['reply_to'] == g.noreply
        text = tasks[0].kwargs['text']
        assert 'Your name was mentioned at [foo]' in text
        assert 'by Test Admin' in text
        assert 'auth/subscriptions#notifications' in text


class TestNotificationTasks(unittest.TestCase):

    def setup_method(self, method):
        setup_basic_test()
        setup_global_objects()

    def test_delivers_messages(self):
        with mock.patch.object(M.Mailbox, 'deliver') as deliver:
            with mock.patch.object(M.Mailbox, 'fire_ready') as fire_ready:
                notification_tasks.notify('42', ['52'], 'none')
                assert deliver.called_with('42', ['52'], 'none')
                assert fire_ready.called_with()


@event_handler('my_event')
def _my_event(event_type, testcase, *args, **kwargs):
    testcase.called_with.append((args, kwargs))


class _TestArtifact(M.Artifact):
    _shorthand_id = FieldProperty(str)
    text = FieldProperty(str)

    def url(self):
        return ''

    def shorthand_id(self):
        return getattr(self, '_shorthand_id', self._id)

    def index(self):
        return dict(
            super().index(),
            text=self.text)


class TestExportTasks(unittest.TestCase):

    def setup_method(self, method):
        setup_basic_test()
        setup_global_objects()
        project = M.Project.query.get(shortname='test')
        shutil.rmtree(project.bulk_export_path(tg.config['bulk_export_path']), ignore_errors=True)

    def teardown_method(self, method):
        project = M.Project.query.get(shortname='test')
        shutil.rmtree(project.bulk_export_path(tg.config['bulk_export_path']), ignore_errors=True)

    def test_bulk_export_filter_exportable(self):
        exportable = mock.Mock(exportable=True)
        not_exportable = mock.Mock(exportable=False)
        BE = export_tasks.BulkExport()
        self.assertEqual(
            BE.filter_exportable([None, exportable, not_exportable]), [exportable])

    def test_bulk_export_filter_successful(self):
        BE = export_tasks.BulkExport()
        self.assertEqual(
            BE.filter_successful(['foo', None, '0']), ['foo', '0'])

    @mock.patch('allura.tasks.export_tasks.shutil')
    @mock.patch('allura.tasks.export_tasks.zipdir')
    @mock.patch.dict(tg.config, {'bulk_export_filename': '{project}.zip'})
    @td.with_wiki
    def test_bulk_export(self, zipdir, shutil):
        M.MonQTask.query.remove()
        export_tasks.bulk_export(['wiki'])
        temp = '/tmp/bulk_export/p/test/test'
        zipfn = '/tmp/bulk_export/p/test/test.zip'
        zipdir.assert_called_with(temp, zipfn)
        shutil.rmtree.assert_called_once_with(six.ensure_binary(temp))
        # check notification
        tasks = M.MonQTask.query.find(
            dict(task_name='allura.tasks.mail_tasks.sendsimplemail')).all()
        assert len(tasks) == 1
        assert (tasks[0].kwargs['subject'] ==
                     'Bulk export for project test completed')
        assert tasks[0].kwargs['fromaddr'] == '"Allura" <noreply@localhost>'
        assert tasks[0].kwargs['reply_to'] == g.noreply
        text = tasks[0].kwargs['text']
        assert 'The bulk export for project test is completed.' in text
        assert 'The following tools were exported:\n- wiki' in text
        assert 'Sample instructions for test' in text

    def test_bulk_export_status(self):
        assert c.project.bulk_export_status() is None
        export_tasks.bulk_export.post(['wiki'])
        assert c.project.bulk_export_status() == 'busy'


class TestAdminTasks(unittest.TestCase):

    def test_install_app_docstring(self):
        assert 'ep_name, mount_point=None' in admin_tasks.install_app.__doc__

Mapper.compile_all()
