# -*- coding: utf-8 -*-
import os
import unittest
import shutil

from ming.orm import ThreadLocalORMSession
from alluratest.controller import setup_basic_test

from allura import model as M
from allura.command.script import ScriptCommand

class TestBackupRestore(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        self.cmd = ScriptCommand('script')
        self.backup_dir = '/tmp/test-backup'

    def tearDown(self):
        if os.path.exists(self.backup_dir):
            shutil.rmtree(self.backup_dir)

    def test_backup(self):
        self._command(
            'test.ini', '../scripts/backup_project.py', 'test', self.backup_dir)
        root = os.listdir(self.backup_dir)
        allura_dir = os.listdir(os.path.join(self.backup_dir, 'allura'))
        project_dir = os.listdir(os.path.join(self.backup_dir, 'project-data'))
        assert 'allura' in root
        assert 'project.bson' in root
        assert 'project-data' in root
        assert 'mailbox.bson' in allura_dir
        assert 'notification.bson' in allura_dir
        assert 'project_role.bson' in allura_dir
        assert 'shortlink.bson' in allura_dir
        assert 'thread.bson' in project_dir
        assert 'config.bson' in project_dir

    def test_purge(self):
        p1 = M.Project.query.get(shortname='test')
        assert p1 is not None
        self._command(
            'test.ini', '../scripts/purge_project.py', 'test')
        assert M.Project.query.find(dict(shortname='test')).count() == 0
        ThreadLocalORMSession.close_all()
        p2= M.Project.query.get(_id=p1._id)
        assert p2 is not None
        assert p2.deleted
        assert p2.name == p1.name
        assert p2.shortname == 'deleted-%s' % p2._id

    def test_restore(self):
        p1 = M.Project.query.get(shortname='test')
        assert p1 is not None
        self._command(
            'test.ini', '../scripts/backup_project.py', 'test', self.backup_dir)
        self._command(
            'test.ini', '../scripts/purge_project.py', 'test')
        self._command(
            'test.ini', '../scripts/restore_project.py', self.backup_dir, 'test2', 'test2')
        assert M.Project.query.find(dict(shortname='test')).count() == 0
        assert M.Project.query.find(dict(shortname='test2')).count() == 1
        ThreadLocalORMSession.close_all()
        p2= M.Project.query.get(_id=p1._id)
        assert p2.shortname == 'test2'
        assert p2.app_configs


    def _command(self, *args):
        try:
            self.cmd.run(list(args))
        except SystemExit, ex:
            assert ex.args == (0,)
