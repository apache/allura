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
    if obj is None: return None
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

def search_artifact(atype, q, history=False, rows=10, **kw):
    # first, grab an artifact and get the fields that it indexes
    a = atype.query.find().first()
    if a is None: return # if there are no instance of atype, we won't find anything
    fields = a.index()
    # Now, we'll translate all the fld:
    for f in fields:
        if f[-2] == '_':
            base = f[:-2]
            actual = f
            q = q.replace(base+':', actual+':')
    fq = [
        'type_s:%s' % fields['type_s'],
        'project_id_s:%s' % c.project._id,
        'mount_point_s:%s' % c.app.config.options.mount_point ]
    if not history:
        fq.append('is_history_b:False')
    return g.solr.search(q, fq=fq)
    
def find_shortlinks(text):
    from pyforge import model as M
    for mo in re_SHORTLINK.finditer(text):
        obj = M.ArtifactLink.lookup(mo.group(1))
        if obj is None: continue
        yield obj

