from logging import getLogger
from itertools import islice

from pylons import c,g
from pprint import pformat

# from pyforge.tasks.search import AddArtifacts, DelArtifacts
from pyforge.lib.helpers import push_config

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
    try:
        text = text + pformat(doc.values())
    except TypeError:
        # log.exception('Indexing empty text: %s', doc)
        text = pformat(doc.values())
    doc['text'] = text
    return doc

def _obj_to_ref(obj):
    return dict(
        project_id=obj.project._id,
        cls=obj.__class__,
        id=obj._id)

def ref_to_solr(ref):
    from pyforge.model import Project
    project = Project.query.get(_id=ref['project_id'])
    with push_config(c, project=project):
        obj = ref['cls'].query.get(_id=ref['id'])
        return _solarize(obj)

@try_solr
def add_artifact(obj):
    add_artifacts([obj])

@try_solr
def add_artifacts(obj_iter):
    def gen_index():
        for obj in obj_iter:
            result = _solarize(obj)
            if result is None:
                continue # uninidexable document
            else:
                yield result
    # artifact_iterator = gen_index()
    artifact_iterator = ( _obj_to_ref(o) for o in obj_iter)
    while True:
        artifacts = list(islice(artifact_iterator, 1000))
        if not artifacts: break
        # Publish using pickle for speed -- this is our
        #   most performance-critical message yet, and it is only Python->Python,
        #   so pickle is appropriate (and we need DateTime, so we can't use json)
        g.publish('react', 'artifacts_altered',
                  dict(artifacts=artifacts),
                  serializer='pickle')

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
    
