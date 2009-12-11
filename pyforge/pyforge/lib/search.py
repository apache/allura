from logging import getLogger

from pylons import g
from pprint import pformat

# from pyforge.tasks.search import AddArtifacts, DelArtifacts

log = getLogger(__name__)

def try_solr(func):
    def inner(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except:
            log.exception('Error in solr indexing')
    return inner

def _solarize(obj):
    doc = obj.index()
    if doc is None: return None
    text = doc.pop('text', '')
    text = text + pformat(doc.values())
    doc['text'] = text
    return doc

@try_solr
def add_artifact(obj):
    add_artifacts([obj])

@try_solr
def add_artifacts(obj_iter):
    obj_iter = list(obj_iter)
    artifacts = [ _solarize(a) for a in obj_iter ]
    for obj, index in zip(obj_iter, artifacts):
        if index is None:
            log.error('Unindexable document: %s (%s): %r',
                      obj, type(obj), obj)
    artifacts = [ a for a in artifacts if a ]
    g.publish('react', 'artifacts_altered',
              dict(artifacts=artifacts),
              serializer='yaml') # json can't handle datetimes

@try_solr
def remove_artifact(obj):
    remove_artifacts([obj])

@try_solr
def remove_artifacts(obj_iter):
    oids = [ obj.index_id()
             for obj in obj_iter ]
    g.publish('react', 'artifacts_removed',
              dict(artifact_ids=oids))

@try_solr
def search(q,**kw):
    return g.solr.search(q, **kw)
    
