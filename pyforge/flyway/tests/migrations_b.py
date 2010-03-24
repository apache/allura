from flyway import Migration
from . import test_globals

for version in range(10):
    class V(Migration):
        version = version
        def up(self):
            test_globals.migrations_run.append((self.module, self.version, 'up'))
        def down(self):
            test_globals.migrations_run.append((self.module, self.version, 'down'))
        def requires(self):
            yield ('a', self.version)
            for req in Migration.requires(self):
                yield req

