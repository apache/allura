from flyway import Migration

for version in range(10):
    class V(Migration):
        version = version
        def up(self): pass
        def down(self):  pass
