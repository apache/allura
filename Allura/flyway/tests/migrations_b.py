from flyway import Migration
from . import test_globals

for version in range(10):
    class V(Migration):
        version = version
        def up(self):
            test_globals.migrations_run.append((self.module, self.version, 'up'))
        def down(self):
            test_globals.migrations_run.append((self.module, self.version, 'down'))
        def up_requires(self):
            yield ('a', self.version)
            for req in Migration.up_requires(self):
                yield req
        def down_requires(self):
            yield ('a', self.version)
            for req in Migration.down_requires(self):
                yield req

