import re
import cPickle as pickle
from logging import getLogger
from pprint import pformat
from itertools import islice, chain

import markdown
from pylons import c,g
import pysolr

from . import helpers as h
from .markdown_extensions import ForgeExtension

# from pyforge.tasks.search import AddArtifacts, DelArtifacts

# re_SHORTLINK = re.compile(ForgeExtension.core_artifact_link)
re_SOLR_ERROR = re.compile(r'<pre>(org.apache.lucene[^:]+: )?(?P<text>[^<]+)</pre>')

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
        for aref in artifacts:
            aname = pickle.loads(aref.artifact_type).__name__
            h.log_action(log, 'upsert artifact').info(
                'upsert artifact %s', aname,
                meta=dict(
                    type=aname,
                    id=aref.artifact_id))
        if not artifacts: break
        g.publish('react', 'artifacts_altered',
                  dict(artifacts=artifacts),
                  serializer='pickle')

@try_solr
def remove_artifacts(obj_iter):
    artifact_iterator = ( o.dump_ref() for o in obj_iter)
    while True:
        artifacts = list(islice(artifact_iterator, 1000))
        for aref in artifacts:
            aname = pickle.loads(aref.artifact_type).__name__
            h.log_action(log, 'delete artifact').info(
                'delete artifact %s', aname,
                meta=dict(
                    type=aname,
                    id=aref.artifact_id))
        if not artifacts: break
        g.publish('react', 'artifacts_removed',
                  dict(artifacts=artifacts),
                  serializer='pickle')

@try_solr
def search(q,**kw):
    return g.solr.search(q, **kw)

def search_artifact(atype, q, history=False, rows=10, **kw):
    """Performs SOLR search.

    Raises ValueError if SOLR returns an error.
    """
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
    try:
        return g.solr.search(q, fq=fq, rows=rows, **kw)
    except pysolr.SolrError, e:
        log.info("Solr error: %s", e)
        m = re_SOLR_ERROR.search(e.message)
        if m:
            text = m.group('text')
        else:
            text = "syntax error?"
        raise ValueError(text)

def find_shortlinks(text):
    md = markdown.Markdown(
        extensions=['codehilite', ForgeExtension(), 'tables'],
        output_format='html4')
    md.convert(text)
    link_index = md.postprocessors['forge'].parent.alinks
    return [ link for link in link_index.itervalues() if link is not None]

