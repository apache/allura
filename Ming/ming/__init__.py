from formencode.variabledecode import variable_decode
import pymongo

from session import Session
from base import Document, Field

# Re-export direction keys
ASCENDING = pymongo.ASCENDING
DESCENDING = pymongo.DESCENDING

def configure(**kwargs):
    from datastore import DataStore
    config = variable_decode(kwargs)
    datastores = dict(
        (name, DataStore(**value))
        for name, value in config['ming'].iteritems())
    Session._datastores = datastores
    # bind any existing sessions
    for name, session in Session._registry.iteritems():
        session.bind = datastores.get(name, None)
