# -*- coding: utf-8 -*-

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

"""
Functional test suite for the root controller.

This is an example of how functional tests can be written for controllers.

As opposed to a unit-test, which test a small unit of functionality,
functional tests exercise the whole application and its WSGI stack.

Please read http://pythonpaste.org/webtest/ for more information.

"""
from __future__ import unicode_literals
from __future__ import absolute_import
import os
from six.moves.urllib.parse import quote

from tg import tmpl_context as c
from nose.tools import assert_equal, assert_in
from ming.orm.ormsession import ThreadLocalORMSession
import mock
from IPython.testing.decorators import module_not_available, skipif

from allura.tests import decorators as td
from allura.tests import TestController
from allura import model as M
from allura.lib import helpers as h
from alluratest.controller import setup_trove_categories


class TestRootController(TestController):

    def setUp(self):
        super(TestRootController, self).setUp()
        n_adobe = M.Neighborhood.query.get(name='Adobe')
        assert n_adobe
        u_admin = M.User.query.get(username='test-admin')
        assert u_admin
        n_adobe.register_project('adobe-2', u_admin)

    def test_index(self):
        response = self.app.get('/', extra_environ=dict(username=str('*anonymous')))
        assert_equal(response.location, 'http://localhost/neighborhood')

        response = self.app.get('/')
        assert_equal(response.location, 'http://localhost/dashboard')

    def test_neighborhood(self):
        response = self.app.get('/neighborhood')
        assert_equal(response.html.find('h2', {'class': 'dark title'}).contents[
                     0].strip(), 'All Neighborhoods')
        nbhds = response.html.findAll('div', {'class': 'nbhd_name'})
        assert nbhds[0].find('a').get('href') == '/adobe/'
        cat_links = response.html.find('div', {'id': 'sidebar'}).findAll('li')
        assert len(cat_links) == 4
        assert cat_links[0].find('a').get('href') == '/browse/clustering'
        assert cat_links[0].find('a').find('span').string == 'Clustering'

    def test_validation(self):
        # this is not configured ON currently, so adding an individual test to get coverage of the validator itself
        with mock.patch.dict(os.environ, ALLURA_VALIDATION='all'):
            self.app.get('/neighborhood')
            self.app.get('/nf/markdown_to_html?markdown=aaa&project=test&app=bugs&neighborhood=%s'
                         % M.Neighborhood.query.get(name='Projects')._id,
                         validate_chunk=True)

    def test_sidebar_escaping(self):
        # use this as a convenient way to get something in the sidebar
        M.ProjectCategory(name='test-xss', label='<script>alert(1)</script>')
        ThreadLocalORMSession.flush_all()

        response = self.app.get('/neighborhood')
        # inject it into the sidebar data
        content = response.html.find('div', {'id': 'content_base'}).prettify()
        assert '<script>' not in content, content
        assert '&lt;script&gt;' in content

    def test_strange_accept_headers(self):
        hdrs = [
            'text/plain;text/html;text/*',
            'text/html,application/xhtml+xml,application/xml;q=0.9;text/plain;q=0.8,image/png,*/*;q=0.5']
        for hdr in hdrs:
            # malformed headers used to return 500, just make sure they don't
            # now
            self.app.get('/', headers=dict(Accept=str(hdr)), validate_skip=True)

    def test_encoded_urls(self):
        # not valid unicode
        self.app.get(b'/foo\xFF', status=400)
        self.app.get('/foo%FF', status=400)
        # encoded
        self.app.get('/foo%C3%A9', status=404)
        self.app.get('/u/foo%C3%A9/profile', status=404)

    def test_project_browse(self):
        com_cat = M.ProjectCategory.query.find(
            dict(label='Communications')).first()
        M.Project.query.find(dict(shortname='adobe-1')
                             ).first().category_id = com_cat._id
        response = self.app.get('/browse')
        assert len(
            response.html.findAll('a', {'href': '/adobe/adobe-1/'})) == 1
        assert len(
            response.html.findAll('a', {'href': '/adobe/adobe-2/'})) == 1
        response = self.app.get('/browse/communications')
        assert len(
            response.html.findAll('a', {'href': '/adobe/adobe-1/'})) == 1
        assert len(
            response.html.findAll('a', {'href': '/adobe/adobe-2/'})) == 0
        response = self.app.get('/browse/communications/fax')
        assert len(
            response.html.findAll('a', {'href': '/adobe/adobe-1/'})) == 0
        assert len(
            response.html.findAll('a', {'href': '/adobe/adobe-2/'})) == 0

    def test_neighborhood_home(self):
        setup_trove_categories()
        # Install home app
        nb = M.Neighborhood.query.get(name='Adobe')
        p = nb.neighborhood_project
        with h.push_config(c, user=M.User.query.get(username='test-admin')):
            p.install_app('home', 'home', 'Home', ordinal=0)

        response = self.app.get('/adobe/')
        projects = response.html.findAll('div', {'class': 'list card proj_icon'})
        assert_equal(len(projects), 2)
        cat_links = response.html.find('div', {'id': 'sidebar'}).findAll('ul')[1].findAll('li')
        assert len(cat_links) == 3, cat_links
        assert cat_links[0].find('a').get('href') == '/adobe/browse/clustering'
        assert cat_links[0].find('a').find('span').string == 'Clustering'

    def test_neighborhood_project_browse(self):
        com_cat = M.ProjectCategory.query.find(
            dict(label='Communications')).first()
        fax_cat = M.ProjectCategory.query.find(dict(label='Fax')).first()
        M.Project.query.find(dict(shortname='adobe-1')
                             ).first().category_id = com_cat._id
        M.Project.query.find(dict(shortname='adobe-2')
                             ).first().category_id = fax_cat._id
        response = self.app.get('/adobe/browse')
        assert len(
            response.html.findAll('a', {'href': '/adobe/adobe-1/'})) == 1
        assert len(
            response.html.findAll('a', {'href': '/adobe/adobe-2/'})) == 1
        response = self.app.get('/adobe/browse/communications')
        assert len(
            response.html.findAll('a', {'href': '/adobe/adobe-1/'})) == 1
        assert len(
            response.html.findAll('a', {'href': '/adobe/adobe-2/'})) == 1
        response = self.app.get('/adobe/browse/communications/fax')
        assert len(
            response.html.findAll('a', {'href': '/adobe/adobe-1/'})) == 0
        assert len(
            response.html.findAll('a', {'href': '/adobe/adobe-2/'})) == 1

    @td.with_wiki
    def test_markdown_to_html(self):
        n = M.Neighborhood.query.get(name='Projects')
        r = self.app.get(
            '/nf/markdown_to_html?markdown=*aaa*bb[wiki:Home]&project=test&app=bugs&neighborhood=%s' % n._id, validate_chunk=True)
        assert '<p><em>aaa</em>bb<a class="alink" href="/p/test/wiki/Home/">[wiki:Home]</a></p>' in r, r

        # this happens to trigger an error
        bad_markdown = '<foo {bar}>'
        r = self.app.get('/nf/markdown_to_html?markdown=%s&project=test&app=bugs&neighborhood=%s' %
                         (quote(bad_markdown), n._id))
        r.mustcontain('The markdown supplied could not be parsed correctly.')
        r.mustcontain('<pre>&lt;foo {bar}&gt;</pre>')

    def test_slash_redirect(self):
        self.app.get('/p', status=301)
        self.app.get('/p/', status=302)

    @skipif(module_not_available('newrelic'))
    def test_newrelic_set_transaction_name(self):
        from allura.controllers.project import NeighborhoodController
        with mock.patch('newrelic.agent.callable_name') as callable_name,\
                mock.patch('newrelic.agent.set_transaction_name') as set_transaction_name:
            callable_name.return_value = 'foo'
            self.app.get('/p/')
            arg = callable_name.call_args[0][0]
            assert_equal(arg.__wrapped__,
                         NeighborhoodController.index.__wrapped__)
            set_transaction_name.assert_called_with('foo')

    def test_error_page(self):
        # hard to force a real error (esp. with middleware debugging being different for tests) but we can hit direct:
        r = self.app.get('/error/document')
        r.mustcontain("We're sorry but we weren't able to process")


class TestRootWithSSLPattern(TestController):
    def setUp(self):
        with td.patch_middleware_config({'force_ssl.pattern': '^/auth'}):
            super(TestRootWithSSLPattern, self).setUp()

    def test_no_weird_ssl_redirect_for_error_document(self):
        # test a 404, same functionality as a 500 from an error
        r = self.app.get('/auth/asdfasdf',
                         extra_environ={'wsgi.url_scheme': str('https')},
                         status=404)
        assert '302 Found' not in r.text, r.text
        assert '/error/document' not in r.text, r.text
