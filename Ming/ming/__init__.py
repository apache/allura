import pymongo

from session import Session
from base import Document
import schema

# Re-export direction keys
ASCENDING = pymongo.ASCENDING
DESCENDING = pymongo.DESCENDING

def bind_sessions(**datastores):
    for name, session in Session._registry.iteritems():
        session.bind = datastores.get(name, None)
