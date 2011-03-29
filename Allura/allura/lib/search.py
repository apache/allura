import re
import cPickle as pickle
from logging import getLogger
from pprint import pformat
from itertools import islice, chain

import markdown
from tg import c,g
import pysolr

from . import helpers as h
from .markdown_extensions import ForgeExtension

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
    q = atype.translate_query(q, fields)
    fq = [
        'type_s:%s' % fields['type_s'],
        'project_id_s:%s' % c.project._id,
        'mount_point_s:%s' % c.app.config.options.mount_point ]
    if not history:
        fq.append('is_history_b:False')
    try:
        return g.solr.search(q, fq=fq, rows=rows, **kw)
    except pysolr.SolrError, e:
        raise ValueError('Error running search query: %s' % e.message)

def find_shortlinks(text):
    md = markdown.Markdown(
        extensions=['codehilite', ForgeExtension(), 'tables'],
        output_format='html4')
    md.convert(text)
    link_index = md.postprocessors['forge'].parent.alinks
    return [ link for link in link_index.itervalues() if link is not None]
