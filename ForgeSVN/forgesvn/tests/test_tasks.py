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

import shutil
import unittest
import os

import tg
import mock
from tg import tmpl_context as c
from paste.deploy.converters import asbool

from alluratest.controller import setup_basic_test

from allura import model as M
from allura.lib import helpers as h
from allura.tasks import repo_tasks

from forgesvn.tests import with_svn


class TestRepoTasks(unittest.TestCase):

    def setup_method(self, method):
        setup_basic_test()
        self.setup_with_tools()
        if asbool(tg.config.get('smtp.mock')):
            self.smtp_mock = mock.patch('allura.lib.mail_util.smtplib.SMTP')
            self.smtp_mock.start()

    def teardown_method(self, method):
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
            assert ns == M.Notification.query.find().count()

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
            f.assert_called_with(
                os.path.join(tg.config['scm.repos.root'], 'svn/p/test/src'),
                ignore_errors=True)
