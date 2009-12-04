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
    text = doc.pop('text', '')
    if text is None:
        import pdb; pdb.set_trace()
    text = text + pformat(doc.values())
    doc['text'] = text
    return doc

@try_solr
def add_artifact(obj):
    add_artifacts([obj])

@try_solr
def add_artifacts(obj_iter):
    g.publish('audit', 'search.add_artifacts',
              dict(artifacts=[_solarize(a) for a in obj_iter]),
              serializer='yaml') # json can't handle datetimes

@try_solr
def remove_artifact(obj):
    remove_artifacts([obj])

@try_solr
def remove_artifacts(obj_iter):
    oids = [ obj.index()['id']
             for obj in obj_iter ]
    g.publish('audit', 'search.del_artifacts',
              dict(artifact_ids=oids))

@try_solr
def search(q,**kw):
    return g.solr.search(q, **kw)
    
