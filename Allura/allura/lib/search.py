import re
import socket
import cPickle as pickle
from logging import getLogger
from pprint import pformat
from itertools import islice, chain

import markdown
from pylons import c,g
from pysolr import SolrError

from . import helpers as h
from .markdown_extensions import ForgeExtension

log = getLogger(__name__)

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

class SearchError(SolrError):
    pass

def search(q,short_timeout=False,ignore_errors=True,**kw):
    try:
        if short_timeout:
            return g.solr_short_timeout.search(q, **kw)
        else:
            return g.solr.search(q, **kw)
    except (SolrError, socket.error) as e:
        log.exception('Error in solr indexing')
        if not ignore_errors:
            match = re.search(r'<pre>(.*)</pre>', str(e))
            raise SearchError('Error running search query: %s' % (match.group(1) if match else e))

def search_artifact(atype, q, history=False, rows=10, short_timeout=False, **kw):
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
    return search(q, fq=fq, rows=rows, short_timeout=short_timeout, ignore_errors=False, **kw)

def find_shortlinks(text):
    md = markdown.Markdown(
        extensions=['codehilite', ForgeExtension(), 'tables'],
        output_format='html4')
    md.convert(text)
    link_index = md.treeprocessors['links'].alinks
    return [ link for link in link_index if link is not None]
