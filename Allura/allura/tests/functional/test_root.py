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
import os
import re
from unittest import skipIf

import pytest
from tg import tmpl_context as c

from allura.tests.decorators import patch_middleware_config
from alluratest.tools import module_not_available
from ming.odm.odmsession import ThreadLocalODMSession
import mock
import tg

from allura.tests import decorators as td
from allura.tests import TestController
from allura import model as M
from allura.lib import helpers as h
from alluratest.controller import setup_trove_categories


def assert_globals_are_reset():
    # in normal tests the globals 'stacks' are cleared
    assert tg.config._object_stack() == []

    # and similarly, 'c' and 'request' TG globals are not even accessible at all
    with pytest.raises(AttributeError):
        c._object_stack()
    assert 'allura.websetup.schema.EmptyClass' in repr(c)  # can't use isinstance/type because it's a proxy

    with pytest.raises(AttributeError) as exc_info:
        tg.request._object_stack()
    assert str(exc_info.value) == 'request', exc_info


class TestRootController(TestController):

    def setup_method(self, method):
        super().setup_method(method)
        n_adobe = M.Neighborhood.query.get(name='Adobe')
        assert n_adobe
        u_admin = M.User.query.get(username='test-admin')
        assert u_admin
        n_adobe.register_project('adobe-2', u_admin)

    def test_index(self):
        response = self.app.get('/', extra_environ=dict(username='*anonymous'))
        assert response.location == 'http://localhost/neighborhood'

        response = self.app.get('/')
        assert response.location == 'http://localhost/dashboard'

        assert_globals_are_reset()  # should be ok, but just to make sure what "normal" is (might change with upgrades)

    def test_neighborhood(self):
        response = self.app.get('/neighborhood')
        assert response.html.find('h2', {'class': 'dark title'}).find('span').contents[
            0].strip() == 'All Neighborhoods'
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
        ThreadLocalODMSession.flush_all()

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
        assert len(projects) == 2
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

    def test_slash_redirect(self):
        self.app.get('/p', status=301)
        self.app.get('/p/', status=302)

    @skipIf(module_not_available('newrelic'), 'requires newrelic')
    def test_newrelic_set_transaction_name(self):
        from allura.controllers.project import NeighborhoodController
        with mock.patch('newrelic.agent.callable_name') as callable_name,\
                mock.patch('newrelic.agent.set_transaction_name') as set_transaction_name:
            callable_name.return_value = 'foo'
            self.app.get('/p/')
            arg = callable_name.call_args[0][0]
            assert arg.__wrapped__ == NeighborhoodController.index.__wrapped__
            set_transaction_name.assert_called_with('foo', priority=2)

    def test_error_page(self):
        # hard to force a real error (esp. with middleware debugging being different for tests) but we can hit direct:
        r = self.app.get('/error/document')
        r.mustcontain("We&#39;re sorry but we weren&#39;t able to process")

    @mock.patch.dict(tg.config, {'csp.frame_sources_enforce': True,
                                 'csp.report_uri_enforce': 'https://example.com/r/d/csp/enforce',
                                 'csp.form_actions_enforce': True,
                                 'csp.script_src_enforce': True})
    def test_headers(self):
        resp = self.app.get('/p')
        expected_headers = "form-action 'self'; frame-src 'self' www.youtube-nocookie.com; object-src 'none';"
        expected_headers += "frame-ancestors 'self'; report-uri https://example.com/r/d/csp/enforce; script-src 'self;"
        csp_headers = resp.headers.getall('Content-Security-Policy')[0]
        assert all([h.strip() in csp_headers for h in expected_headers.split(';')])

    @mock.patch.dict(tg.config, {'csp.frame_sources_enforce': True,
                                 'csp.report_uri_enforce': 'https://example.com/r/d/csp/enforce'})
    def test_headers_config(self):
        resp = self.app.get('/p')
        assert "frame-src 'self' www.youtube-nocookie.com" in resp.headers.getall('Content-Security-Policy')[0]

    @mock.patch.dict(tg.config, {'csp.report_uri': 'https://example.com/r/d/csp/reportOnly'})
    def test_headers_report(self):
        resp = self.app.get('/p/wiki/Home/')
        expected_headers = "report-uri https://example.com/r/d/csp/reportOnly;"
        expected_headers += "frame-src 'self' www.youtube-nocookie.com; script-src 'self' ;"
        expected_headers += "form-action 'self'"

        csp_headers = resp.headers.getall('Content-Security-Policy-Report-Only')[0]
        assert all([h.strip() in csp_headers for h in expected_headers.split(';')])

    @mock.patch.dict(tg.config, {'csp.report_uri_enforce': 'https://example.com/r/d/csp/enforce',
                                 'csp.frame_sources_enforce': True})
    def test_headers_frame_sources_enforce(self):
        resp = self.app.get('/p/wiki/Home/')
        expected_headers = "report-uri https://example.com/r/d/csp/enforce;"
        expected_headers += "frame-src 'self' www.youtube-nocookie.com;"
        expected_headers += "object-src 'none'"
        expected_report_headers = "script-src 'self' ;  form-action 'self'"
        csp_headers = resp.headers.getall('Content-Security-Policy')[0]
        csp_report_headers = resp.headers.getall('Content-Security-Policy-Report-Only')[0]
        assert all([h.strip() in csp_headers for h in expected_headers.split(';')])
        assert all([h.strip() in csp_report_headers for h in expected_report_headers.split(';')])


class TestRootWithSSLPattern(TestController):
    def setup_method(self, method):
        with td.patch_middleware_config({'force_ssl.pattern': '^/auth'}):
            super().setup_method(method)

    def test_no_weird_ssl_redirect_for_error_document(self):
        # test a 404, same functionality as a 500 from an error
        r = self.app.get('/auth/asdfasdf',
                         extra_environ={'wsgi.url_scheme': 'https'},
                         status=404)
        assert '302 Found' not in r.text, r.text
        assert '301 Moved Permanently' not in r.text, r.text
        assert '/error/document' not in r.text, r.text


class TestErrorMiddleware(TestController):
    def setup_method(self):
        with patch_middleware_config({
            # this makes all the middleware get used (normally override_root=basetest_project_root makes it skip some)
            'override_root': None,
            'debug': 'false',
        }):
            super().setup_method()

    def test_404_error(self):
        r = self.app.get('/this-is-a-404', status=404)
        assert r.content_type == 'text/html'
        r.mustcontain('404 Error has Occurred')  # in error.html
        r.mustcontain('This project is powered by')  # in master template

        # Ensure 404 handling with StatusCodeRedirect doesn't leave anything behind
        assert_globals_are_reset()

    def test_error_nodebug(self):
        with mock.patch.object(M.Project, 'ordered_mounts') as function_nbhd_controller_calls:
            function_nbhd_controller_calls.side_effect = Exception('forced an error!')
            r = self.app.get('/p/',
                             # suppress ErrorMiddleware from throwing the error, we want it to trap & return 500 page
                             extra_environ={'paste.throw_errors': False},
                             status=500,
                             expect_errors=True,  # because stderr gets error details printed to it
                             )
        assert r.status_code == 500
        assert r.content_type == 'text/html'
        r.mustcontain('500 Error has Occurred')  # in error.html
        r.mustcontain('This project is powered by')  # in master template

        # error logging from ErrorMiddleware
        assert 'Exception: forced an error!' in r.errors
        assert 'Allura/allura/controllers/project.py' in r.errors
        assert 'CGI Variables' in r.errors
        assert "PATH_INFO: '/p/'" in r.errors
