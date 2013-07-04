# -*- coding: utf-8 -*-

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

import os
import operator
import shutil
import sys
import unittest
from base64 import b64encode
import logging

import tg
import mock
from pylons import tmpl_context as c, app_globals as g
from datadiff.tools import assert_equal
from nose.tools import assert_in
from ming.orm import FieldProperty, Mapper
from ming.orm import ThreadLocalORMSession
from testfixtures import LogCapture
from IPython.testing.decorators import onlyif

from alluratest.controller import setup_basic_test, setup_global_objects

from allura import model as M
from allura.lib import helpers as h
from allura.lib import search
from allura.lib.exceptions import CompoundError
from allura.tasks import event_tasks
from allura.tasks import index_tasks
from allura.tasks import mail_tasks
from allura.tasks import notification_tasks
from allura.tasks import repo_tasks
from allura.tasks import export_tasks
from allura.tests import decorators as td
from allura.lib.decorators import event_handler, task


class TestRepoTasks(unittest.TestCase):
    @mock.patch('allura.tasks.repo_tasks.c.app')
    @mock.patch('allura.tasks.repo_tasks.g.post_event')
    def test_clone_posts_event_on_failure(self, post_event, app):
        fake_source_url = 'fake_source_url'
        fake_traceback = 'fake_traceback'
        app.repo.init_as_clone.side_effect = Exception(fake_traceback)
        repo_tasks.clone(None, None, fake_source_url)
        assert_equal(post_event.call_args[0][0], 'repo_clone_task_failed')
        assert_equal(post_event.call_args[0][1], fake_source_url)
        assert_equal(post_event.call_args[0][2], None)
        # ignore args[3] which is a traceback string


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
        with LogCapture(level=logging.ERROR) as l:
            t()
        # l.check() would be nice, but string is too detailed to check
        assert_equal(l.records[0].name, 'allura.model.monq_model')
        msg = l.records[0].getMessage()
        assert_in("AssertionError('assert 0',)", msg)
        assert_in("AssertionError('assert 5',)", msg)
        assert_in(' on job <MonQTask ', msg)
        assert_in(' (error) P:10 allura.tests.test_tasks.raise_exc ', msg)
        for x in range(10):
            assert ('assert %d' % x) in t.result

class TestIndexTasks(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        setup_global_objects()

    @td.with_wiki
    def test_add_artifacts(self):
        from allura.lib.search import find_shortlinks
        with mock.patch('allura.lib.search.find_shortlinks') as find_slinks:
            find_slinks.side_effect = lambda s: find_shortlinks(s)

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
            assert_equal(find_slinks.call_args_list,
                    [mock.call(a.index().get('text')) for a in artifacts])

    @td.with_wiki
    @mock.patch('allura.tasks.index_tasks.g.solr')
    def test_del_artifacts(self, solr):
        old_shortlinks = M.Shortlink.query.find().count()
        artifacts = [ _TestArtifact(_shorthand_id='ta_%s' % x) for x in range(5) ]
        M.artifact_orm_session.flush()
        arefs = [ M.ArtifactReference.from_artifact(a) for a in artifacts ]
        ref_ids = [ r._id for r in arefs ]
        M.artifact_orm_session.flush()
        index_tasks.add_artifacts(ref_ids)
        M.main_orm_session.flush()
        M.main_orm_session.clear()
        new_shortlinks = M.Shortlink.query.find().count()
        assert old_shortlinks + 5 == new_shortlinks, 'Shortlinks not created'
        assert solr.add.call_count == 1
        sort_key = operator.itemgetter('id')
        assert_equal(
                sorted(solr.add.call_args[0][0], key=sort_key),
                sorted([search.solarize(ref.artifact) for ref in arefs],
                        key=sort_key))
        index_tasks.del_artifacts(ref_ids)
        M.main_orm_session.flush()
        M.main_orm_session.clear()
        new_shortlinks = M.Shortlink.query.find().count()
        assert old_shortlinks == new_shortlinks, 'Shortlinks not deleted'
        solr_query = 'id:({0})'.format(' || '.join(ref_ids))
        solr.delete.assert_called_once_with(q=solr_query)


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

    def test_send_email_with_disabled_user(self):
        c.user = M.User.by_username('test-admin')
        c.user.disabled = True
        destination_user = M.User.by_username('test-user-1')
        destination_user.preferences['email_address'] = 'user1@mail.com'
        ThreadLocalORMSession.flush_all()
        with mock.patch.object(mail_tasks.smtp_client, '_client') as _client:
            mail_tasks.sendmail(
                fromaddr=str(c.user._id),
                destinations=[ str(destination_user._id) ],
                text=u'This is a test',
                reply_to=u'noreply@sf.net',
                subject=u'Test subject',
                message_id=h.gen_message_id())
            assert_equal(_client.sendmail.call_count, 1)
            return_path, rcpts, body = _client.sendmail.call_args[0]
            body = body.split('\n')
            assert_in('From: noreply@in.sf.net', body)

    def test_send_email_with_disabled_destination_user(self):
        c.user = M.User.by_username('test-admin')
        destination_user = M.User.by_username('test-user-1')
        destination_user.preferences['email_address'] = 'user1@mail.com'
        destination_user.disabled = True
        ThreadLocalORMSession.flush_all()
        with mock.patch.object(mail_tasks.smtp_client, '_client') as _client:
            mail_tasks.sendmail(
                fromaddr=str(c.user._id),
                destinations=[ str(destination_user._id) ],
                text=u'This is a test',
                reply_to=u'noreply@sf.net',
                subject=u'Test subject',
                message_id=h.gen_message_id())
            assert_equal(_client.sendmail.call_count, 0)

    def test_sendsimplemail_with_disabled_user(self):
        c.user = M.User.by_username('test-admin')
        with mock.patch.object(mail_tasks.smtp_client, '_client') as _client:
            mail_tasks.sendsimplemail(
                fromaddr=str(c.user._id),
                toaddr='test@mail.com',
                text=u'This is a test',
                reply_to=u'noreply@sf.net',
                subject=u'Test subject',
                message_id=h.gen_message_id())
            assert_equal(_client.sendmail.call_count, 1)
            return_path, rcpts, body = _client.sendmail.call_args[0]
            body = body.split('\n')
            assert_in('From: "Test Admin" <test-admin@users.localhost>', body)

            c.user.disabled = True
            ThreadLocalORMSession.flush_all()
            mail_tasks.sendsimplemail(
                fromaddr=str(c.user._id),
                toaddr='test@mail.com',
                text=u'This is a test',
                reply_to=u'noreply@sf.net',
                subject=u'Test subject',
                message_id=h.gen_message_id())
            assert_equal(_client.sendmail.call_count, 2)
            return_path, rcpts, body = _client.sendmail.call_args[0]
            body = body.split('\n')
            assert_in('From: noreply@in.sf.net', body)

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


class TestExportTasks(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        setup_global_objects()
        project = M.Project.query.get(shortname='test')
        shutil.rmtree(project.bulk_export_path(), ignore_errors=True)

    def tearDown(self):
        project = M.Project.query.get(shortname='test')
        shutil.rmtree(project.bulk_export_path(), ignore_errors=True)

    @mock.patch('allura.tasks.export_tasks.log')
    def test_bulk_export_invalid_project(self, log):
        export_tasks.bulk_export('bad', [u'wiki'])
        log.error.assert_called_once_with('Project bad not found')

    @mock.patch('allura.tasks.export_tasks.log')
    def test_bulk_export_invalid_tool(self, log):
        export_tasks.bulk_export('test', [u'bugs', u'blog'])
        assert_equal(log.info.call_count, 2)
        assert_equal(log.info.call_args_list, [
            mock.call('Can not load app for bugs mount point. Skipping.'),
            mock.call('Can not load app for blog mount point. Skipping.')])

    @mock.patch('allura.tasks.export_tasks.log')
    @td.with_tool('test', 'Tickets', 'bugs')
    @td.with_tool('test', 'Blog', 'blog')
    def test_bulk_export_not_exportable_tool(self, log):
        export_tasks.bulk_export('test', [u'bugs', u'blog'])
        assert_equal(log.info.call_count, 2)
        assert_equal(log.info.call_args_list, [
            mock.call('Tool bugs is not exportable. Skipping.'),
            mock.call('Tool blog is not exportable. Skipping.')])

    @mock.patch('allura.tasks.export_tasks.shutil')
    @mock.patch('allura.tasks.export_tasks.zipdir')
    @mock.patch('forgewiki.wiki_main.ForgeWikiApp.bulk_export')
    @mock.patch('allura.tasks.export_tasks.log')
    @td.with_wiki
    def test_bulk_export(self, log, wiki_bulk_export, zipdir, shutil):
        export_tasks.bulk_export('test', [u'wiki'])
        assert_equal(log.info.call_count, 1)
        assert_equal(log.info.call_args_list, [
            mock.call('Exporting wiki...')])
        wiki_bulk_export.assert_called_once()
        temp = '/tmp/bulk_export/p/test/test'
        zipfn = '/tmp/bulk_export/p/test/test.zip'
        zipdir.assert_caled_once_with(temp, temp + '/test.zip')
        shutil.move.assert_called_once_with(temp + '/test.zip',  zipfn)
        shutil.rmtree.assert_called_once_with(temp)

    @mock.patch('forgewiki.wiki_main.ForgeWikiApp.bulk_export')
    @mock.patch('allura.tasks.export_tasks.log')
    @td.with_wiki
    def test_bulk_export_quits_if_another_export_is_running(self, log, wiki_bulk_export):
        project = M.Project.query.get(shortname='test')
        export_tasks.create_export_dir(project)
        assert_equal(project.bulk_export_status(), 'busy')
        export_tasks.bulk_export('test', [u'wiki'])
        log.info.assert_called_once_with('Another export is running for project test. Skipping.')
        assert_equal(wiki_bulk_export.call_count, 0)

    def test_create_export_dir(self):
        project = M.Project.query.get(shortname='test')
        export_path = project.bulk_export_path()
        path = export_tasks.create_export_dir(project)
        assert_equal(path, '/tmp/bulk_export/p/test/test')
        assert os.path.exists(os.path.join(export_path, project.shortname))

    @onlyif(os.path.exists(tg.config.get('scm.repos.tarball.zip_binary', '/usr/bin/zip')), 'zip binary is missing')
    def test_zip_and_cleanup(self):
        project = M.Project.query.get(shortname='test')
        export_path = project.bulk_export_path()
        path = export_tasks.create_export_dir(project)
        export_tasks.zip_and_cleanup(project)
        assert not os.path.exists(path)
        assert os.path.exists(os.path.join(export_path, 'test.zip'))

    def test_bulk_export_status(self):
        project = M.Project.query.get(shortname='test')
        assert_equal(project.bulk_export_status(), None)

        export_tasks.create_export_dir(project)
        assert_equal(project.bulk_export_status(), 'busy')

        with open(os.path.join(project.bulk_export_path(),
                               project.bulk_export_filename()), 'w') as f:
            f.write('just test')
        assert_equal(project.bulk_export_status(), 'ready')


Mapper.compile_all()
