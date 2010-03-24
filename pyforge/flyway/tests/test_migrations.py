import unittest
import test_globals
from flyway.command import MigrateCommand

class MigrateTest(unittest.TestCase):

    def setUp(self):
        test_globals.migrations_run = []
        self.cmd = MigrateCommand('flyway')
        self.cmd.entry_point_section='flyway.test_migrations'
        self.args = [
            '-u', 'mongo://127.0.0.1:27017/pyforge',
            ]
        self.cmd.run(self.args + ['--reset'])

    def test_simple(self):
        self.cmd.run(self.args)
        expected_migrations = [
            (ab, ver, 'up') for ver in range(10) for ab in 'ab']
        assert expected_migrations == test_globals.migrations_run

    def test_only_a(self):
        self.cmd.run(self.args + ['a'])
        expected_migrations = [
            ('a', ver, 'up') for ver in range(10) ]
        assert expected_migrations == test_globals.migrations_run

    def test_b_requires_a(self):
        self.cmd.run(self.args + ['b'])
        expected_migrations = [
            (ab, ver, 'up') for ver in range(10) for ab in 'ab']
        assert expected_migrations == test_globals.migrations_run

    def test_downgrade(self):
        self.cmd.run(self.args)
        self.cmd.run(self.args + ['a=5'])
        # Migrate up
        expected_migrations = [
            (ab, ver, 'up') for ver in range(10) for ab in 'ab']
        # Migrate a down
        expected_migrations += [
            ('a', 9, 'down'), ('a', 8, 'down'), ('a', 7, 'down'), ('a', 6, 'down') ]
        assert expected_migrations == test_globals.migrations_run

    def test_stuck_migration(self):
        self.cmd.run(self.args + ['a']) # a=9, b=-1 now
        # Can't migrate b because it requires a=0, which is unsatisfiable (we do
        # not support downgrading a automagically so as to upgrade b)
        self.assertRaises(ValueError, self.cmd.run, self.args + ['b'])
