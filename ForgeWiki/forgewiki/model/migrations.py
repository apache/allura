from flyway import Migration

class CurrentVersion(Migration):
    version = 1

    def up(self): pass
    def down(self): pass
