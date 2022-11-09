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

import unittest

import mock
from markupsafe import Markup

from allura.lib import helpers as h
from allura.tests import decorators as td
from alluratest.controller import setup_basic_test
from allura.lib.solr import Solr, escape_solr_arg
from allura.lib.search import search_app, SearchIndexable


class TestSolr(unittest.TestCase):

    def setup_method(self, method):
        # need to create the "test" project so @td.with_wiki works
        setup_basic_test()

    @mock.patch('allura.lib.solr.pysolr')
    def test_init(self, pysolr):
        servers = ['server1', 'server2']
        solr = Solr(servers, commit=False, commitWithin='10000')
        calls = [mock.call('server1'), mock.call('server2')]
        pysolr.Solr.assert_has_calls(calls)
        assert len(solr.push_pool) == 2

        pysolr.reset_mock()
        solr = Solr(servers, 'server3', commit=False, commitWithin='10000')
        calls = [mock.call('server1'), mock.call('server2'),
                 mock.call('server3')]
        pysolr.Solr.assert_has_calls(calls)
        assert len(solr.push_pool) == 2

    @mock.patch('allura.lib.solr.pysolr')
    def test_add(self, pysolr):
        servers = ['server1', 'server2']
        solr = Solr(servers, commit=False, commitWithin='10000')
        solr.add('foo', commit=True, commitWithin=None)
        calls = [mock.call('foo', commit=True, commitWithin=None)] * 2
        pysolr.Solr().add.assert_has_calls(calls)
        pysolr.reset_mock()
        solr.add('bar', somekw='value')
        calls = [mock.call('bar', commit=False,
                           commitWithin='10000', somekw='value')] * 2
        pysolr.Solr().add.assert_has_calls(calls)

    @mock.patch('allura.lib.solr.pysolr')
    def test_delete(self, pysolr):
        servers = ['server1', 'server2']
        solr = Solr(servers, commit=False, commitWithin='10000')
        solr.delete('foo', commit=True)
        calls = [mock.call('foo', commit=True)] * 2
        pysolr.Solr().delete.assert_has_calls(calls)
        pysolr.reset_mock()
        solr.delete('bar', somekw='value')
        calls = [mock.call('bar', commit=False, somekw='value')] * 2
        pysolr.Solr().delete.assert_has_calls(calls)

    @mock.patch('allura.lib.solr.pysolr')
    def test_commit(self, pysolr):
        servers = ['server1', 'server2']
        solr = Solr(servers, commit=False, commitWithin='10000')
        solr.commit('arg')
        pysolr.Solr().commit.assert_has_calls([mock.call('arg')] * 2)
        pysolr.reset_mock()
        solr.commit('arg', kw='kw')
        calls = [mock.call('arg', kw='kw')] * 2
        pysolr.Solr().commit.assert_has_calls(calls)

    @mock.patch('allura.lib.solr.pysolr')
    def test_search(self, pysolr):
        servers = ['server1', 'server2']
        solr = Solr(servers, commit=False, commitWithin='10000')
        solr.search('foo')
        solr.query_server.search.assert_called_once_with('foo')
        pysolr.reset_mock()
        solr.search('bar', kw='kw')
        solr.query_server.search.assert_called_once_with('bar', kw='kw')

    @mock.patch('allura.lib.search.search')
    def test_site_admin_search(self, search):
        from allura.lib.search import site_admin_search
        from allura.model import Project, User
        fq = ['type_s:Project']
        site_admin_search(Project, 'test', 'shortname', rows=25)
        search.assert_called_once_with(
            'shortname_s:(test)', fq=fq, ignore_errors=False, rows=25, **{'q.op': 'AND'})

        search.reset_mock()
        site_admin_search(Project, 'shortname:test || shortname:test2', '__custom__')
        search.assert_called_once_with(
            'shortname_s:test || shortname_s:test2', fq=fq, ignore_errors=False)

        fq = ['type_s:User']
        search.reset_mock()
        site_admin_search(User, 'test-user', 'username', rows=25)
        search.assert_called_once_with(
            'username_s:(test-user)', fq=fq, ignore_errors=False, rows=25, **{'q.op': 'AND'})

        search.reset_mock()
        site_admin_search(User, 'username:admin1 || username:root', '__custom__')
        search.assert_called_once_with(
            'username_s:admin1 || username_s:root', fq=fq, ignore_errors=False)


class TestSearchIndexable(unittest.TestCase):

    def setup_method(self, method):
        self.obj = SearchIndexable()

    def test_solarize_empty_index(self):
        self.obj.index = lambda: None
        assert self.obj.solarize() is None

    def test_solarize_doc_without_text(self):
        self.obj.index = lambda: dict()
        assert self.obj.solarize() == dict(text='')

    def test_solarize_strips_markdown(self):
        self.obj.index = lambda: dict(text='# Header')
        assert self.obj.solarize() == dict(text='Header')

    def test_solarize_html_in_text(self):
        self.obj.index = lambda: dict(text='<script>a(1)</script>')
        assert self.obj.solarize() == dict(text='<script>a(1)</script>')
        self.obj.index = lambda: dict(text='&lt;script&gt;a(1)&lt;/script&gt;')
        assert self.obj.solarize() == dict(text='<script>a(1)</script>')


class TestSearch_app(unittest.TestCase):

    def setup_method(self, method):
        # need to create the "test" project so @td.with_wiki works
        setup_basic_test()

    @td.with_wiki
    @mock.patch('allura.lib.search.url')
    @mock.patch('allura.lib.search.request')
    def test_basic(self, req, url_fn):
        req.GET = dict()
        req.path = '/test/search'
        url_fn.side_effect = ['the-score-url', 'the-date-url']
        with h.push_context('test', 'wiki', neighborhood='Projects'):
            resp = search_app(q='foo bar')
        assert resp == dict(
            q='foo bar',
            history=None,
            results=[],
            count=0,
            limit=25,
            page=0,
            search_error=None,
            sort_score_url='the-score-url',
            sort_date_url='the-date-url',
            sort_field='score',
        )

    @td.with_wiki
    @mock.patch('allura.lib.search.g.solr.search')
    @mock.patch('allura.lib.search.url')
    @mock.patch('allura.lib.search.request')
    def test_escape_solr_text(self, req, url_fn, solr_search):
        req.GET = dict()
        req.path = '/test/wiki/search'
        url_fn.side_effect = ['the-score-url', 'the-date-url']
        results = mock.Mock(hits=2, docs=[
            {'id': 123, 'type_s': 'WikiPage Snapshot',
             'url_s': '/test/wiki/Foo', 'version_i': 2},
            {'id': 321, 'type_s': 'Post'},
        ], highlighting={
            123: dict(
                title='some #ALLURA-HIGHLIGHT-START#Foo#ALLURA-HIGHLIGHT-END# stuff',
                text='scary <script>alert(1)</script> bar'),
            321: dict(title='blah blah',
                      text='less scary but still dangerous &lt;script&gt;alert(1)&lt;/script&gt; '
                      'blah #ALLURA-HIGHLIGHT-START#bar#ALLURA-HIGHLIGHT-END# foo foo'),
        },
        )
        results.__iter__ = lambda self: iter(results.docs)
        results.__len__ = lambda self: len(results.docs)
        solr_search.return_value = results
        with h.push_context('test', 'wiki', neighborhood='Projects'):
            resp = search_app(q='foo bar')

        assert resp == dict(
            q='foo bar',
            history=None,
            count=2,
            limit=25,
            page=0,
            search_error=None,
            sort_score_url='the-score-url',
            sort_date_url='the-date-url',
            sort_field='score',
            results=[{
                'id': 123,
                'type_s': 'WikiPage Snapshot',
                'version_i': 2,
                'url_s': '/test/wiki/Foo?version=2',
                # highlighting works
                'title_match': Markup('some <strong>Foo</strong> stuff'),
                # HTML in the solr plaintext results get escaped
                'text_match': Markup('scary &lt;script&gt;alert(1)&lt;/script&gt; bar'),
                '_artifact': None,
            }, {
                'id': 321,
                'type_s': 'Post',
                'title_match': Markup('blah blah'),
                # highlighting in text
                'text_match': Markup('less scary but still dangerous &amp;lt;script&amp;gt;alert(1)&amp;lt;/script&amp;gt; blah <strong>bar</strong> foo foo'),
                '_artifact': None,
            }]
        )

    def test_escape_solr_arg(self):
        text = 'some: weird "text" with symbols'
        escaped_text = escape_solr_arg(text)
        assert escaped_text == r'some\: weird \"text\" with symbols'

    def test_escape_solr_arg_with_backslash(self):
        text = 'some: weird "text" with \\ backslash'
        escaped_text = escape_solr_arg(text)
        assert escaped_text == r'some\: weird \"text\" with \\ backslash'
