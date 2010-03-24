import logging

log = logging.getLogger(__name__)

class MigrationMeta(type):
    '''Metaclass providing a registry of migrations.

    If the class-level variable _current_migrations_module is
    defined, then migrations will be registered according to that
    module and their declared version.  (The migrate command
    sets this module according to the migration's entry point name.)
    '''

    def __init__(cls, name, bases, dct):
        if cls._current_migrations_module is None: return
        cls.migrations_registry[
            cls._current_migrations_module, cls.version] = cls
        cls.module = cls._current_migrations_module

    def get(cls, module, version):
        '''Load a Migration class from the registry'''
        return cls.migrations_registry[module, version]

    def latest_versions(cls):
        result = {}
        for k,v in cls.migrations_registry:
            if result.get(k, -1) < v:
                result[k] = v
        return result

class Migration(object):
    __metaclass__ = MigrationMeta
    version = 0
    module = None # filled in automatically by Metaclass
    migrations_registry = {}
    _current_migrations_module = None


    def __init__(self, session):
        self.session = session

    def requires(self):
        '''Returns a list of requirements that must be met before upgrading to
        this migration.  By default, returns the previous-versioned migration'''
        return [ (self.module, self.version-1) ]

    def up(self):
        '''Upgrade to a new schema version'''
        raise NotImplementedError, 'up'

    def down(self):
        '''Downgrade from this schema version (undo an 'up') '''
        raise NotImplementedError, 'down'

    def ensure_index(self, cls, fields, **kwargs):
        '''Ensures that a particular index has been created in the DB'''
        self.session.ensure_index(cls, fields, **kwargs)

    def drop_index(self, cls, fields):
        '''Ensures that a particular index has been dropped from  the DB'''
        self.session.drop_index(cls, fields)

    def set_indexes(self, cls):
        '''Ensures that a the only indexes on a class are those defined in its
        __mongometa__ attribute.'''
        self.session.drop_indexes(cls)
        self.session.ensure_indexes(cls)

