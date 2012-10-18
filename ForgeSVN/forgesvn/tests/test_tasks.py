# -*- coding: utf-8 -*-
import shutil
import unittest

import tg
import mock
from pylons import c
from ming.orm import ThreadLocalORMSession
from paste.deploy.converters import asbool

from alluratest.controller import setup_basic_test, setup_global_objects

from allura import model as M
from allura.lib import helpers as h
from allura.tasks import repo_tasks

from forgesvn.tests import with_svn

class TestRepoTasks(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        self.setup_with_tools()
        if asbool(tg.config.get('smtp.mock')):
            self.smtp_mock = mock.patch('allura.lib.mail_util.smtplib.SMTP')
            self.smtp_mock.start()
        
    def tearDown(self):
        if asbool(tg.config.get('smtp.mock')):
            self.smtp_mock.stop()

    @with_svn
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
            f.assert_called_with('foo', 'bar', 'baz', False)
            assert ns + 1 == M.Notification.query.find().count()

    def test_refresh(self):
        with mock.patch.object(c.app.repo, 'refresh') as f:
            repo_tasks.refresh()
            f.assert_called_with()

    def test_uninstall(self):
        with mock.patch.object(shutil, 'rmtree') as f:
            repo_tasks.uninstall()
            f.assert_called_with('/tmp/svn/p/test/src', ignore_errors=True)
