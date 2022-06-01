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


import ast
import re
import socket
from logging import getLogger


import bson
import markdown
import jinja2
import markupsafe
from tg import redirect, url
from tg import tmpl_context as c, app_globals as g
from tg import request
from pysolr import SolrError

from allura.lib import helpers as h
from allura.lib.solr import escape_solr_arg
from allura.lib.utils import urlencode
import six

log = getLogger(__name__)


class SearchIndexable:

    """
    Base class for anything you want to search on.
    """

    def index_id(self):
        """
        Should return a globally unique object identifier.

        Used for SOLR ID, shortlinks, and possibly elsewhere.
        """
        id = '{}.{}#{}'.format(
            self.__class__.__module__,
            self.__class__.__name__,
            self._id)
        return id.replace('.', '/')

    def index(self):
        """
        Return a :class:`dict` representation of this object suitable for
        search indexing.

        Subclasses should implement this, providing a dictionary of solr_field => value.
        These fields & values will be stored by Solr.  Subclasses should call the
        super().index() and then extend it with more fields.

        You probably want to override at least title and text to have
        meaningful search results and email senders.

        You can take advantage of Solr's dynamic field typing by adding a type
        suffix to your field names, e.g.:

            _s (string) (not analyzed)
            _t (text) (analyzed)
            _b (bool)
            _i (int)
            _f (float)
            _dt (datetime)

        """
        raise NotImplementedError

    def should_update_index(self, old_doc, new_doc):
        """Determines if solr index should be updated.

        Values passed as old_doc and new_doc are original and modified
        versions of same object, represented as dictionaries.
        """
        return old_doc != new_doc

    def solarize(self):
        doc = self.index()
        if doc is None:
            return None
        # if index() returned doc without text, assume empty text
        text = doc.get('text')
        if text is None:
            text = doc['text'] = ''

        # Convert text to plain text (It usually contains markdown markup).
        # To do so, we convert markdown into html, and then strip all html tags.
        text = g.markdown.convert(text)
        doc['text'] = markupsafe.Markup.escape(text).striptags()

        # convert some date/time field types to str
        # from https://github.com/django-haystack/pysolr/blob/1a8887cb2ce1c30ef9d6570704254b4520f8a959/pysolr.py#L692
        for k, value in doc.items():
            if hasattr(value, "strftime"):
                if hasattr(value, "hour"):
                    offset = value.utcoffset()
                    if offset:
                        value = value - offset
                    value = value.replace(tzinfo=None).isoformat() + "Z"
                else:
                    value = "%sT00:00:00Z" % value.isoformat()
                doc[k] = value

        return doc

    @classmethod
    def translate_query(cls, q, fields):
        """Return a translated Solr query (``q``), where generic field
        identifiers are replaced by the 'strongly typed' versions defined in
        ``fields``.

        """
        # Replace longest fields first to avoid problems when field names have
        # the same suffixes, but different field types. E.g.:
        # query 'shortname:test' with fields.keys() == ['name_t', 'shortname_s']
        # will be translated to 'shortname_t:test', which makes no sense
        fields = sorted(list(fields.keys()), key=len, reverse=True)
        for f in fields:
            if '_' in f:
                base, typ = f.rsplit('_', 1)
                q = q.replace(base + ':', f + ':')
        return q


class SearchError(SolrError):
    pass


def inject_user(q, user=None):
    '''Replace $USER with current user's name.'''
    if user is None:
        user = c.user
    return q.replace('$USER', '"%s"' % user.username) if q else q


def search(q, short_timeout=False, ignore_errors=True, **kw):
    q = inject_user(q)
    try:
        if short_timeout:
            return g.solr_short_timeout.search(q, **kw)
        else:
            return g.solr.search(q, **kw)
    except (SolrError, OSError) as e:
        log.exception('Error in solr search')
        if not ignore_errors:
            match = re.search(r'<pre>(.*)</pre>', str(e))
            raise SearchError('Error running search query: %s' %
                              (match.group(1) if match else e))


def search_artifact(atype, q, history=False, rows=10, short_timeout=False, filter=None, **kw):
    """Performs SOLR search.

    Raises SearchError if SOLR returns an error.
    """
    # first, grab an artifact and get the fields that it indexes
    a = atype.query.find().first()
    if a is None:
        return  # if there are no instance of atype, we won't find anything
    fields = a.index()
    fq = ['type_s:%s' % fields['type_s']]
    # Now, we'll translate all the fld:
    if c.app is not None:
        q = atype.translate_query(q, fields)
        fq.append('mount_point_s:%s' % c.app.config.options.mount_point)
    else:
        q = SearchIndexable.translate_query(q, fields)

    if c.project is not None:
        fq.append('project_id_s:%s' % c.project._id)

    fq += kw.pop('fq', [])
    if isinstance(filter, str):  # may be stringified after a ticket filter, then bulk edit
        filter = ast.literal_eval(filter)
    if isinstance(filter, dict):
        for name, values in (filter or {}).items():
            field_name = name + '_s'
            parts = []
            for v in values:
                # Specific solr syntax for empty fields
                if v == '' or v is None:
                    part = f'(-{field_name}:[* TO *] AND *:*)'
                else:
                    part = f'{field_name}:{escape_solr_arg(v)}'
                parts.append(part)
            fq.append(' OR '.join(parts))
    if not history:
        fq.append('is_history_b:False')
    return search(q, fq=fq, rows=rows, short_timeout=short_timeout, ignore_errors=False, **kw)


def site_admin_search(model, q, field, **kw):
    """Performs SOLR search for a given model.

    Raises SearchError if SOLR returns an error.
    """
    # first, grab an object and get the fields that it indexes
    obj = model.query.find().first()
    if obj is None:
        return  # if there are no objects, we won't find anything
    fields = obj.index()
    if field == '__custom__':
        # custom query -> query as is
        q = obj.translate_query(q, fields)
    else:
        # construct query for a specific selected field
        # use parens to group all the parts of the query with the field
        # escaping spaces with '\ ' isn't sufficient for display_name_t since its stored as text_general (why??)
        # and wouldn't handle foo@bar.com split on @ either
        # This should work, but doesn't for unknown reasons: q = u'{!term f=%s}%s' % (field, q)
        q = obj.translate_query(f'{field}:({q})', fields)
        kw['q.op'] = 'AND'  # so that all terms within the () are required
    fq = ['type_s:%s' % model.type_s]
    return search(q, fq=fq, ignore_errors=False, **kw)


def search_app(q='', fq=None, app=True, **kw):
    """Helper for app/project search.

    Uses dismax query parser. Matches on `title` and `text`. Handles paging, sorting, etc
    """
    from allura.model import ArtifactReference
    from allura.lib.security import has_access

    history = kw.pop('history', None)
    if app and kw.pop('project', False):
        # Used from app's search controller. If `project` is True, redirect to
        # 'entire project search' page
        redirect(c.project.url() + 'search/?' +
                 urlencode(dict(q=q, history=history)))
    search_comments = kw.pop('search_comments', None)
    limit = kw.pop('limit', None)
    page = kw.pop('page', 0)
    default = kw.pop('default', 25)
    allowed_types = kw.pop('allowed_types', [])
    parser = kw.pop('parser', None)
    sort = kw.pop('sort', 'score desc')
    fq = fq if fq else []
    search_error = None
    results = []
    count = 0
    matches = {}
    limit, page, start = g.handle_paging(limit, page, default=default)
    if not q:
        q = ''
    else:
        # Match on both `title` and `text` by default, using 'dismax' parser.
        # Score on `title` matches is boosted, so title match is better than body match.
        # It's 'fuzzier' than standard parser, which matches only on `text`.
        if search_comments:
            allowed_types += ['Post']
        if app:
            fq = [
                'project_id_s:%s' % c.project._id,
                'mount_point_s:%s' % c.app.config.options.mount_point,
                '-deleted_b:true',
                'type_s:(%s)' % ' OR '.join(
                    ['"%s"' % t for t in allowed_types])
            ] + fq
        search_params = {
            'qt': 'dismax',
            'qf': 'title^2 text',
            'pf': 'title^2 text',
            'fq': fq,
            'hl': 'true',
            'hl.simple.pre': '#ALLURA-HIGHLIGHT-START#',
            'hl.simple.post': '#ALLURA-HIGHLIGHT-END#',
            'sort': sort,
        }
        if not history:
            search_params['fq'].append('is_history_b:False')
        if parser == 'standard':
            search_params.pop('qt', None)
            search_params.pop('qf', None)
            search_params.pop('pf', None)
        try:
            results = search(
                q, short_timeout=True, ignore_errors=False,
                rows=limit, start=start, **search_params)
        except SearchError as e:
            search_error = e
        if results:
            count = results.hits
            matches = results.highlighting

            def historize_urls(doc):
                if doc.get('type_s', '').endswith(' Snapshot'):
                    if doc.get('url_s'):
                        doc['url_s'] = doc['url_s'] + \
                            '?version=%s' % doc.get('version_i')
                return doc

            def add_matches(doc):
                m = matches.get(doc['id'], {})
                title = h.get_first(m, 'title')
                text = h.get_first(m, 'text')
                if title:
                    title = (markupsafe.escape(title)
                                   .replace('#ALLURA-HIGHLIGHT-START#', markupsafe.Markup('<strong>'))
                                   .replace('#ALLURA-HIGHLIGHT-END#', markupsafe.Markup('</strong>')))
                if text:
                    text = (markupsafe.escape(text)
                                  .replace('#ALLURA-HIGHLIGHT-START#', markupsafe.Markup('<strong>'))
                                  .replace('#ALLURA-HIGHLIGHT-END#', markupsafe.Markup('</strong>')))
                doc['title_match'] = title
                doc['text_match'] = text or h.get_first(doc, 'text')
                return doc

            def paginate_comment_urls(doc):
                if doc.get('type_s', '') == 'Post':
                    artifact = doc['_artifact']
                    if artifact:
                        doc['url_paginated'] = artifact.url_paginated()
                return doc

            def filter_unauthorized(doc):
                aref = ArtifactReference.query.get(_id=doc.get('id'))
                # cache for paginate_comment_urls to re-use
                doc['_artifact'] = aref and aref.artifact
                # .primary() necessary so that a ticket's comment for example is checked with the ticket's perms
                if doc['_artifact'] and not has_access(doc['_artifact'].primary(), 'read', c.user):
                    return None
                else:
                    return doc

            filtered_results = [_f for _f in map(filter_unauthorized, results) if _f]
            count -= len(results) - len(filtered_results)
            results = filtered_results
            results = map(historize_urls, results)
            results = map(add_matches, results)
            results = map(paginate_comment_urls, results)

    # Provide sort urls to the view
    score_url = 'score desc'
    date_url = 'mod_date_dt desc'
    try:
        field, order = sort.split(' ')
    except ValueError:
        field, order = 'score', 'desc'
    sort = ' '.join([field, 'asc' if order == 'desc' else 'desc'])
    if field == 'score':
        score_url = sort
    elif field == 'mod_date_dt':
        date_url = sort
    params = request.GET.copy()
    params.update({'sort': score_url})
    score_url = url(request.path, params=params)
    params.update({'sort': date_url})
    date_url = url(request.path, params=params)
    return dict(q=q, history=history, results=list(results) or [],
                count=count, limit=limit, page=page, search_error=search_error,
                sort_score_url=score_url, sort_date_url=date_url,
                sort_field=field)


def find_shortlinks(text):
    from .markdown_extensions import ForgeExtension

    md = markdown.Markdown(
        extensions=['markdown.extensions.codehilite', ForgeExtension(), 'markdown.extensions.tables'],
        output_format='html')
    md.convert(text)
    link_index = md.treeprocessors['links'].alinks
    return [link for link in link_index if link is not None]


def artifacts_from_index_ids(index_ids, model, objectid_id=True):
    '''
    :param list[str] index_ids: a list of search/subscription/artifact-reference index_id values
    :param type model: the Artifact class
    :param bool objectid_id: whether the _id values are ObjectIds
    :return: instances of the model, for each id given
    :rtype: list
    '''
    # this could be made more flexible to not require the model passed in
    ids = [index_id.split('#')[1] for index_id in index_ids]
    if objectid_id:
        ids = [bson.ObjectId(_id) for _id in ids if _id != 'None']
    return model.query.find({'_id': {'$in': ids}}).all()


def mapped_artifacts_from_index_ids(index_ids, model, objectid_id=True):
    '''
    :param list[str] index_ids: a list of search/subscription/artifact-reference index_id values
    :param type model: the Artifact class
    :param bool objectid_id: whether the _id values are ObjectIds
    :return: instances of the model, keyed by str(_id)
    :rtype: dict
    '''
    models = artifacts_from_index_ids(index_ids, model, objectid_id=objectid_id)
    map = {}
    for m in models:
        map[str(m._id)] = m
    return map