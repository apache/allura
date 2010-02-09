import re
from logging import getLogger
from pprint import pformat
from itertools import islice, chain

from pylons import c,g

from .markdown_extensions import ForgeExtension

# from pyforge.tasks.search import AddArtifacts, DelArtifacts

re_SHORTLINK = re.compile(ForgeExtension.core_artifact_link)

log = getLogger(__name__)

def try_solr(func):
    def inner(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except: # pragma no cover
            log.exception('Error in solr indexing')
    return inner

def solarize(obj):
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

@try_solr
def add_artifacts(obj_iter):
    artifact_iterator = ( o.dump_ref() for o in obj_iter)
    while True:
        artifacts = list(islice(artifact_iterator, 1000))
        if not artifacts: break
        g.publish('react', 'artifacts_altered',
                  dict(artifacts=artifacts),
                  serializer='pickle')

@try_solr
def remove_artifacts(obj_iter):
    artifact_iterator = ( o.dump_ref() for o in obj_iter)
    while True:
        artifacts = list(islice(artifact_iterator, 1000))
        if not artifacts: break
        g.publish('react', 'artifacts_removed',
                  dict(artifacts=artifacts),
                  serializer='pickle')

@try_solr
def search(q,**kw):
    return g.solr.search(q, **kw)
    
def find_shortlinks(text):
    from pyforge import model as M
    for mo in re_SHORTLINK.finditer(text):
        obj = M.ArtifactLink.lookup(mo.group(1))
        if obj is None: continue
        yield obj

