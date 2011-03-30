from flyway import Migration

class CurrentVersion(Migration):
    version = 5
    def up(self): pass
    def down(self): pass
