from flyway import Migration

class CurrentVersion(Migration):
    version = 14

    def up(self): pass
    def down(self): pass
