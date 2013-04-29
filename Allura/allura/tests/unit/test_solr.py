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
from nose.tools import assert_equal
from markupsafe import Markup

from allura.lib import helpers as h
from allura.tests import decorators as td
from alluratest.controller import setup_basic_test
from allura.lib.solr import Solr
from allura.lib.search import solarize, search_app

class TestSolr(unittest.TestCase):
    @mock.patch('allura.lib.solr.pysolr')
    def setUp(self, pysolr):
        self.solr = Solr('server', commit=False, commitWithin='10000')

    @mock.patch('allura.lib.solr.pysolr')
    def test_add(self, pysolr):
        s = self.solr
        s.add('foo', commit=True, commitWithin=None)
        pysolr.Solr.add.assert_called_once_with(s, 'foo', commit=True,
                commitWithin=None)
        pysolr.reset_mock()
        s.add('bar', somekw='value')
        pysolr.Solr.add.assert_called_once_with(s, 'bar', commit=False,
                commitWithin='10000', somekw='value')

    @mock.patch('allura.lib.solr.pysolr')
    def test_delete(self, pysolr):
        s = self.solr
        s.delete('foo', commit=True)
        pysolr.Solr.delete.assert_called_once_with(s, 'foo', commit=True)
        pysolr.reset_mock()
        s.delete('bar', somekw='value')
        pysolr.Solr.delete.assert_called_once_with(s, 'bar', commit=False,
                somekw='value')

class TestSolarize(unittest.TestCase):

    def test_no_object(self):
        assert_equal(solarize(None), None)

    def test_empty_index(self):
        obj = mock.MagicMock()
        obj.index.return_value = None
        assert_equal(solarize(obj), None)

    def test_doc_without_text(self):
        obj = mock.MagicMock()
        obj.index.return_value = {}
        assert_equal(solarize(obj), {'text': ''})

    def test_strip_markdown(self):
        obj = mock.MagicMock()
        obj.index.return_value = {'text': '# Header'}
        assert_equal(solarize(obj), {'text': 'Header'})

    def test_html_in_text(self):
        obj = mock.MagicMock()
        obj.index.return_value = {'text': '<script>alert(1)</script>'}
        assert_equal(solarize(obj), {'text': ''})

        obj.index.return_value = {'text': '&lt;script&gt;alert(1)&lt;/script&gt;'}
        assert_equal(solarize(obj), {'text': '<script>alert(1)</script>'})


class TestSearch_app(unittest.TestCase):

    def setUp(self):
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
        assert_equal(resp, dict(
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
        ))

    @td.with_wiki
    @mock.patch('allura.lib.search.g.solr.search')
    @mock.patch('allura.lib.search.url')
    @mock.patch('allura.lib.search.request')
    def test_escape_solr_text(self, req, url_fn, solr_search):
        req.GET = dict()
        req.path = '/test/wiki/search'
        url_fn.side_effect = ['the-score-url', 'the-date-url']
        results = mock.Mock(hits=2, docs=[
                {'id': 123, 'type_s':'WikiPage Snapshot', 'url_s':'/test/wiki/Foo', 'version_i':2},
                {'id': 321, 'type_s':'Post'},
            ], highlighting={
                123: dict(title='some #ALLURA-HIGHLIGHT-START#Foo#ALLURA-HIGHLIGHT-END# stuff',
                         text='scary <script>alert(1)</script> bar'),
                321: dict(title='blah blah',
                         text='less scary but still dangerous &lt;script&gt;alert(1)&lt;/script&gt; '
                              'blah #ALLURA-HIGHLIGHT-START#bar#ALLURA-HIGHLIGHT-END# foo foo'),
            },
        )
        results.__iter__ = lambda self: iter(results.docs)
        solr_search.return_value = results
        with h.push_context('test', 'wiki', neighborhood='Projects'):
            resp = search_app(q='foo bar')

        assert_equal(resp, dict(
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
                }, {
                'id': 321,
                'type_s': 'Post',
                'title_match': Markup('blah blah'),
                # highlighting in text
                'text_match': Markup('less scary but still dangerous &amp;lt;script&amp;gt;alert(1)&amp;lt;/script&amp;gt; blah <strong>bar</strong> foo foo'),
                }]
        ))
