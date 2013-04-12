#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

import re
import socket
from logging import getLogger

import markdown
from pylons import tmpl_context as c, app_globals as g
from pysolr import SolrError

from .markdown_extensions import ForgeExtension

log = getLogger(__name__)

def solarize(obj):
    if obj is None: return None
    doc = obj.index()
    if doc is None: return None
    # if index() returned doc without text, assume empty text
    if not doc.get('text'):
        doc['text'] = ''
    return doc

class SearchError(SolrError):
    pass

def inject_user(q, user=None):
    '''Replace $USER with current user's name.'''
    if user is None:
        user = c.user
    return q.replace('$USER', '"%s"' % user.username) if q else q

def search(q,short_timeout=False,ignore_errors=True,**kw):
    q = inject_user(q)
    try:
        if short_timeout:
            return g.solr_short_timeout.search(q, **kw)
        else:
            return g.solr.search(q, **kw)
    except (SolrError, socket.error) as e:
        log.exception('Error in solr search')
        if not ignore_errors:
            match = re.search(r'<pre>(.*)</pre>', str(e))
            raise SearchError('Error running search query: %s' % (match.group(1) if match else e))

def search_artifact(atype, q, history=False, rows=10, short_timeout=False, **kw):
    """Performs SOLR search.

    Raises SearchError if SOLR returns an error.
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
