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

    def up_requires(self):
        return [ (self.module, self.version-1) ]

    def down_requires(self):
        return [ (self.module, self.version) ]

    def up_postcondition(self):
        return { self.module: self.version }

    def down_postcondition(self):
        return { self.module: self.version-1 }

    def up(self): # pragma no cover
        '''Upgrade to a new schema version'''
        raise NotImplementedError, 'up'

    def down(self): # pragma no cover
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

