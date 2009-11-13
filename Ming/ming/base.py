import decimal
import hashlib
from datetime import datetime
from collections import defaultdict

import pymongo

class Object(dict):
    'Dict providing object-like attr access'
    def __init__(self, *l, **kw):
        dict.__init__(self, *l, **kw)

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError, name

    def __setattr__(self, name, value):
        if name in self.__class__.__dict__:
            dict.__setattr__(self, name, value)
        else:
            self.__setitem__(name, value)

    @classmethod
    def from_bson(cls, bson):
        if isinstance(bson, dict):
            return Object(
                (k, Object.from_bson(v))
                for k,v in bson.iteritems())
        elif isinstance(bson, list):
            return [
                Object.from_bson(v)
                for v in bson ]
        else:
            return bson

    def make_safe(self):
        safe_self = _safe_bson(self)
        self.update(safe_self)

class Field(object):

    def __init__(self, field_type, *args, **kwargs):
        self.type = field_type
        self.args = args
        self.kwargs = kwargs
        self.name = None

    def __get__(self, instance, cls):
        try:
            return instance[self.name]
        except KeyError:
            raise AttributeError, self.name

    def __set__(self, instance, value):
        instance[self.name] = value

    def __delete__(self, instance):
        del instance[self.name]

class ManagerDescriptor(object):
    '''Python descriptor to provide a way to add the .m. attribute to mapped
    classes (which is a Manager - see below) such that the object at the
    attribute "knows" which instance it's attached to.'''

    def __init__(self, mgr_cls):
        self.mgr_cls = mgr_cls

    def __get__(self, instance, cls):
        return self.mgr_cls(instance, cls)

class Manager(object):
    '''Simple class that proxies a bunch of commands to the Session object for
    the managed class/instance.'''

    def __init__(self, instance, cls):
        self.session = cls.__mongometa__.session
        self.instance = instance
        self.cls = cls

    def __call__(self, session):
        '''In order to use an alternate session, just use Class.mgr(other_session)'''
        result = Manager(self.instance, self.cls)
        result.session = session
        return result

    def get(self, **kwargs):
        """
        Returns one matching record, or None
        e.g.
            get(source='sf.net',shortname='foo')
        """
        return self.session.get(self.cls, **kwargs)

    def find(self, *args, **kwargs):
        """
        spec=None, fields=None, ...
        http://api.mongodb.org/python/0.15.1/pymongo.collection.Collection-class.html#find
        e.g.
            find({"source": "sf.net"})
            find({"source": "sf.net"},['shortname'])  # only return shortname fields
        """
        return self.session.find(self.cls, *args, **kwargs)

    def remove(self, *args, **kwargs):
        """
        remove(spec_or_object_id)
        """
        return self.session.remove(self.cls, *args, **kwargs)

    def find_by(self, **kwargs):
        """
        same as find(spec=kwargs)
        e.g.
            find_by(source='sf.net', foo='bar')
        """
        return self.session.find_by(self.cls, **kwargs)

    def count(self):
        return self.session.count(self.cls)

    def ensure_index(self, fields):
        return self.session.ensure_index(self.cls, fields)

    def ensure_indexes(self):
        return self.session.ensure_indexes(self.cls)

    def group(self, *args, **kwargs):
        return self.session.group(self.cls, *args, **kwargs)

    def update_partial(self, spec, fields, upsert=False):
        return self.session.update_partial(self.cls, spec, fields, upsert)

    def save(self, *args):
        """
        Acts on object instance
        e.g.
            cp = model.CustomPage(...)
            cp['foo'] = 3
            cp.m.save()
        with parameters, only sets specified fields
            cp.m.save('foo')
        """
        return self.session.save(self.instance, *args)

    def insert(self):
        """
        Acts on object instance
        e.g.
            model.CustomPage(...).m.insert()
        """
        return self.session.insert(self.instance)

    def update(self, spec, upsert=False):
        """
        Acts on object instance
        e.g.
            model.CustomPage(...).m.update({'foo':'bar'})
        """
        return self.session.update(self.instance, spec, upsert)

    def delete(self):
        """
        Acts on object instance
        e.g.
            model.CustomPage(...).m.delete()
        """
        return self.session.delete(self.instance)

    def set(self, fields_values):
        """
        Acts on object instance
        e.g.
            model.CustomPage(...).m.set({'foo':'bar'})
        """
        return self.session.set(self.instance, fields_values)
    
    def increase_field(self, **kwargs):
        """
        Acts on object instance
        Sets a field to value, only if value is greater than the current value
        Does not change it locally
        e.g.
            model.GlobalSettings.instance().increase_field(key=value)
        """
        return self.session.increase_field(self.instance, **kwargs)

    def migrate(self):
        '''Load each object in the collection and immediately save it.
        '''
        for m in self.find({}):
            m.m.save()

class DocumentMeta(type):
    '''Metaclass for Documents providing several services:

    - the __mongometa__ attribute of the class is modified so that it subclasses
      the __mongometa__ attributes of the Document's base classes (i.e. "class
      Child.__mongometa__(Parent.__mongometa__)
    - The "special" __mongometa__ attribute "schema" will extend, not override
      parent __mongometa__'s "schema" attributes
    - The class is added to a polymorphic registry to allow for polymorphic
      loading from the DB if it specifies which field is its polymorphic
      discriminator ("polymorphic_on")
    '''

    def __init__(cls, name, bases, dct):
        from . import schema
        # Build mongometa (make it inherit from base classes' mongometas
        mm_bases = []
        for base in bases:
            mm = getattr(base, '__mongometa__', None)
            if mm is None: continue
            mm_bases.append(mm)
        mm_dict = {}
        if hasattr(cls, '__mongometa__'):
            mm_dict.update(cls.__mongometa__.__dict__)
        mm = cls.__mongometa__ = type('__mongometa__', tuple(mm_bases), mm_dict)
        if not hasattr(mm, 'polymorphic_on'):
            mm.polymorphic_on = None
            mm.polymorphic_registry = None
        # Make sure mongometa's schema incorporates base schemas
        my_schema = schema.Object()
        for base in mm_bases:
            if hasattr(base, 'schema'):
                if base.schema:
                    my_schema.extend(schema.SchemaItem.make(base.schema))
        if mm.schema:
            my_schema.extend(schema.SchemaItem.make(mm.schema))
        # Collect fields
        for k,v in dct.iteritems():
            if isinstance(v, Field):
                v.name = k
                si = schema.SchemaItem.make(v.type, *v.args, **v.kwargs)
                my_schema.fields[k] = si
        if not my_schema.fields:
            mm.schema = None
        else:
            polymorphic_identity = mm_dict.get('polymorphic_identity', cls.__name__)
            mm.schema = my_schema
            mm.schema.managed_class = cls
            mm.schema.set_polymorphic(
                mm.polymorphic_on, mm.polymorphic_registry, polymorphic_identity)
        
class Document(Object):
    '''Base class for all mapped MongoDB objects (the Document class can be
    thought of as the "collection", where a Document instance is a "document".
    '''
    __metaclass__=DocumentMeta
    _registry = defaultdict(list)
    m = ManagerDescriptor(Manager)
    class __mongometa__:
        '''Supply various information on how the class is mapped without
        polluting the class's namespace.  In particular,

        name - collection name
        session - Session object managing the object (link to a DataStore)
        indexes - list of field name tuples specifying which indexes should exist
                  for the document
        schema - (optional) schema object (augmented with any SchemaItems in the
                                           class dict)
        polymorphic_on - (optional) field name that specifies the concrete class
                         of each document in a polymorphic collection
        polymorphic_identity - (optional) value that should be in the
                               polymorphic_on field to specify that the concrete
                               class is the current one (if unspecified, the
                               class's __name__ attribute is used)
        '''
        name=None
        session=None
        schema=None
        indexes=[]

    def __init__(self, data):
        data = Object.from_bson(data)
        dict.update(self, data)

    @classmethod
    def make(cls, data, allow_extra=False, strip_extra=True):
        'Kind of a virtual constructor'
        if cls.__mongometa__.schema:
            return cls.__mongometa__.schema.validate(
                data, allow_extra=allow_extra, strip_extra=strip_extra)
        else:
            return cls(data)

class Cursor(object):
    '''Python class proxying a MongoDB cursor, constructing and validating
    objects that it tracks
    '''

    def __init__(self, cls, cursor):
        self.cls = cls
        self.cursor = cursor

    def __iter__(self):
        return self

    def __len__(self):
        return self.count()

    def next(self):
        bson = self.cursor.next()
        if bson is None: return None
        return self.cls.make(bson, allow_extra=False, strip_extra=True)

    def count(self):
        return self.cursor.count()

    def limit(self, limit):
        self.cursor = self.cursor.limit(limit)
        return self

    def skip(self, skip):
        self.cursor = self.cursor.skip(skip)
        return self

    def hint(self, index_or_name):
        self.cursor = self.cursor.hint(index_or_name)
        return self

    def sort(self, *args, **kwargs):
        self.cursor = self.cursor.sort(*args, **kwargs)
        return self

    def one(self):
        try:
            result = self.next()
        except StopIteration:
            raise ValueError, 'Less than one result from .one()'
        try:
            self.next()
        except StopIteration:
            return result
        raise ValueError, 'More than one result from .one()'

    def first(self):
        try:
            return self.next()
        except StopIteration:
            return None

    def all(self):
        return list(self)
    
def _safe_bson(obj):
    '''Verify that the obj is safe for bsonification (in particular, no tuples or
    Decimal objects
    '''
    if isinstance(obj, list):
        return map(_safe_bson, obj)
    elif isinstance(obj, dict):
        return Object((k, _safe_bson(v)) for k,v in obj.iteritems())
    elif isinstance(obj, (basestring, int, long, float, datetime)):
        return obj
    elif isinstance(obj, decimal.Decimal):
        return float(obj)
    elif obj is None:
        return obj
    elif isinstance(obj, pymongo.objectid.ObjectId):
        return obj
    else:
        assert False, '%s is not safe for bsonification' % type(obj)

