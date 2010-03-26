import unittest
import test_globals
from flyway.command import MigrateCommand
from flyway.migrate import Migration

class MigrateTest(unittest.TestCase):

    def setUp(self):
        test_globals.migrations_run = []
        # Migration.migrations_registry = {}
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

    def test_downup_migration(self):
        self.cmd.run(self.args + ['a']) # a=9, b=-1 now
        self.cmd.run(self.args + ['b']) # a=9, b=9 now
        expected = [('a', ver, 'up') for ver in range(10) ]
        expected += [('a', ver, 'down') for ver in range(9, 0, -1) ]
        expected.append(('b', 0, 'up'))
        expected += [
            (ab, ver, 'up') for ver in range(1, 10) for ab in 'ab']
        assert expected == test_globals.migrations_run

