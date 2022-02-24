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


import json
import logging

from tg import config
from paste.deploy.converters import asbool
import pysolr
import six

from allura.lib.helpers import shlex_split

log = logging.getLogger(__name__)


escape_rules = {'+': r'\+',
                '-': r'\-',
                '&': r'\&',
                '|': r'\|',
                '!': r'\!',
                '(': r'\(',
                ')': r'\)',
                '{': r'\{',
                '}': r'\}',
                '[': r'\[',
                ']': r'\]',
                '^': r'\^',
                '~': r'\~',
                '*': r'\*',
                '?': r'\?',
                ':': r'\:',
                '"': r'\"',
                ';': r'\;'}


def escape_solr_arg(term):
    """ Apply escaping to the passed in query terms
        escaping special characters like : , etc"""
    term = term.replace('\\', r'\\')   # escape \ first
    for char, escaped_char in escape_rules.items():
        term = term.replace(char, escaped_char)

    return term


def make_solr_from_config(push_servers, query_server=None, **kwargs):
    """
    Make a :class:`Solr <Solr>` instance from config defaults.  Use
    `**kwargs` to override any value
    """
    solr_kwargs = dict(
        commit=asbool(config.get('solr.commit', True)),
        commitWithin=config.get('solr.commitWithin'),
        timeout=int(config.get('solr.long_timeout', 60)),
    )
    solr_kwargs.update(kwargs)
    return Solr(push_servers, query_server, **solr_kwargs)


class Solr:

    """Solr interface that pushes updates to multiple solr instances.

    `push_servers`: list of servers to push to.
    `query_server`: server to read from. Uses `push_servers[0]` if not specified.

    Also, accepts default values for `commit` and `commitWithin`
    and passes those values through to each `add` and `delete` call,
    unless explicitly overridden.
    """

    def __init__(self, push_servers, query_server=None,
                 commit=True, commitWithin=None, **kw):
        self.push_pool = [pysolr.Solr(s, **kw) for s in push_servers]
        if query_server:
            self.query_server = pysolr.Solr(query_server, **kw)
        else:
            self.query_server = self.push_pool[0]
        self._commit = commit
        self.commitWithin = commitWithin

    def add(self, *args, **kw):
        if 'commit' not in kw:
            kw['commit'] = self._commit
        if self.commitWithin and 'commitWithin' not in kw:
            kw['commitWithin'] = self.commitWithin
        responses = []
        for solr in self.push_pool:
            responses.append(solr.add(*args, **kw))
        return responses

    def delete(self, *args, **kw):
        if 'commit' not in kw:
            kw['commit'] = self._commit
        responses = []
        for solr in self.push_pool:
            responses.append(solr.delete(*args, **kw))
        return responses

    def commit(self, *args, **kw):
        responses = []
        for solr in self.push_pool:
            responses.append(solr.commit(*args, **kw))
        return responses

    def search(self, *args, **kw):
        return self.query_server.search(*args, **kw)


class MockSOLR:

    class MockHits(list):

        @property
        def hits(self):
            return len(self)

        @property
        def docs(self):
            return self

        @property
        def facets(self):
            return {'facet_fields': {}}

    def __init__(self):
        self.db = {}

    def add(self, objects):
        for o in objects:
            o['text'] = ''.join(o['text'])
            json.dumps(o)  # ensure no errors (since pysolr 3.9+ uses json API to solr)
            self.db[o['id']] = o

    def commit(self):
        pass

    def search(self, q, fq=None, **kw):
        if q is None:
            q = ''  # shlex will hang on None
        # Parse query
        preds = []
        q_parts = shlex_split(q)
        if fq:
            q_parts += fq
        for part in q_parts:
            if part in ('&&', 'AND'):
                continue
            if part in ('||', 'OR'):
                log.warn(f"MockSOLR doesn't implement OR yet; treating as AND. q={q} fq={fq}")
                continue
            if ':' in part:
                field, value = part.split(':', 1)
                if value.startswith('(') and value.endswith(')'):
                    value = value[1:-1]
                preds.append((field, value))
            else:
                preds.append(('text', part))
        result = self.MockHits()
        for obj in self.db.values():
            for field, value in preds:
                neg = False
                if field[0] in ('!', '-'):
                    neg = True
                    field = field[1:]
                if field == 'text' or field.endswith('_t'):
                    if (value not in str(obj.get(field, ''))) ^ neg:
                        break
                elif field.endswith('_b'):
                    if (asbool(value) != obj.get(field, False)) ^ neg:
                        break
                else:
                    if (value != str(obj.get(field, ''))) ^ neg:
                        break
            else:
                result.append(obj)

        if asbool(kw.get('hl')):
            result.highlighting = {}
        return result

    def delete(self, *args, **kwargs):
        if kwargs.get('q', None) == '*:*':
            self.db = {}
        elif kwargs.get('id', None):
            del self.db[kwargs['id']]
        elif kwargs.get('q', None):
            for doc in self.search(kwargs['q']):
                self.delete(id=doc['id'])
