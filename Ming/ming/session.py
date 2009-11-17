import pymongo

from base import Cursor, Object

class Session(object):
    _registry = {}
    _datastores = {}

    def __init__(self, bind=None):
        self.bind = bind

    @classmethod
    def by_name(cls, name):
        if name in cls._registry:
            result = cls._registry[name]
        else:
            result = cls._registry[name] = cls(cls._datastores.get(name))
        return result

    def _impl(self, cls):
        try:
            return self.bind.db[cls.__mongometa__.name]
        except TypeError:
            return None

    def get(self, cls, **kwargs):
        bson = self._impl(cls).find_one(kwargs)
        if bson is None: return None
        return cls.make(bson)

    def find(self, cls, *args, **kwargs):
        cursor = self._impl(cls).find(*args, **kwargs)
        return Cursor(cls, cursor)

    def remove(self, cls, *args, **kwargs):
        self._impl(cls).remove(*args, **kwargs)

    def find_by(self, cls, **kwargs):
        return self.find(cls, kwargs)

    def count(self, cls):
        return self._impl(cls).count()

    def ensure_index(self, cls, fields, **kwargs):
        if not isinstance(fields, (list, tuple)):
            fields = [ fields ]
        index_fields = [(f, pymongo.ASCENDING) for f in fields]
        return self._impl(cls).ensure_index(index_fields, **kwargs)

    def ensure_indexes(self, cls):
        for idx in getattr(cls.__mongometa__, 'indexes', []):
            self.ensure_index(cls, idx)
        for idx in getattr(cls.__mongometa__, 'unique_indexes', []):
            self.ensure_index(cls, idx, unique=True)

    def group(self, cls, *args, **kwargs):
        return self._impl(cls).group(*args, **kwargs)

    def update_partial(self, cls, spec, fields, upsert):
        return self._impl(cls).update(spec, fields, upsert, safe=True)

    def save(self, doc, *args):
        doc.make_safe()
        if doc.__mongometa__.schema is not None:
            data = doc.__mongometa__.schema.validate(doc)
        else:
            data = dict(doc)
        doc.update(data)
        if args:
            values = dict((arg, data[arg]) for arg in args)
            result = self._impl(doc).update(dict(_id=doc._id), {'$set':values})
        else:
            result = self._impl(doc).save(data, safe=True)
        if result:
            doc._id = result

    def insert(self, doc):
        doc.make_safe()
        if doc.__mongometa__.schema is not None:
            data = doc.__mongometa__.schema.validate(doc)
        else:
            data = dict(doc)
        doc.update(data)
        bson = self._impl(doc).insert(data, safe=True)
        if isinstance(bson, pymongo.objectid.ObjectId):
            doc.update(_id=bson)

    def update(self, doc, spec, upsert=False):
        doc.make_safe()
        if doc.__mongometa__.schema is not None:
            data = doc.__mongometa__.schema.validate(doc)
        else:
            data = dict(doc)
        doc.update(data)
        self._impl(doc).update(doc, spec, upsert, safe=True)

    def delete(self, doc):
        self._impl(doc).remove({'_id':doc._id})

    def set(self, doc, fields_values):
        """
        sets a key/value pairs, and persists those changes to the datastore immediately
        """
        fields_values = Object.from_bson(fields_values)
        fields_values.make_safe()
        doc.update(fields_values)
        impl = self._impl(doc)
        impl.update({'_id':doc._id}, {'$set':fields_values})
        
    def increase_field(self, doc, **kwargs):
        """
        usage: increase_field(key=value)
        Sets a field to value, only if value is greater than the current value
        Does not change it locally
        """
        key = kwargs.keys()[0]
        value = kwargs[key]
        if value is None:
            raise ValueError, "%s=%s" % (key, value)
        
        if key not in doc:
            self._impl(doc).update(
                {'_id': doc._id, key: None},
                {'$set': {key: value}}
            )
        self._impl(doc).update(
            {'_id': doc._id, key: {'$lt': value}},
            # failed attempt at doing it all in one operation
            #{'$where': "this._id == '%s' && (!(%s in this) || this.%s < '%s')"
            #    % (doc._id.url_encode(), key, key, value)},
            {'$set': {key: value}}
        )
