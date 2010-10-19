# -*- coding: utf-8 -*-
"""
Functional test suite for the root controller.

This is an example of how functional tests can be written for controllers.

As opposed to a unit-test, which test a small unit of functionality,
functional tests exercise the whole application and its WSGI stack.

Please read http://pythonpaste.org/webtest/ for more information.

"""
from nose.tools import assert_true

from allura.tests import TestController
from allura import model as M
from ming.orm import session
from urllib import quote

class TestRootController(TestController):
    def test_index(self):
        response = self.app.get('/')
        assert response.html.find('h1',{'class':'title'}).string == 'All Projects'
        projects = response.html.findAll('div',{'class':'border card'})
        assert projects[0].find('a').get('href') == '/adobe/adobe-1/'
        assert projects[0].find('img').get('alt') == 'adobe-1 Logo'
        cat_links = response.html.find('div',{'id':'sidebar'}).findAll('li')
        assert len(cat_links) == 4
        assert cat_links[0].find('a').get('href') == '/browse/clustering'
        assert cat_links[0].find('a').get('class') == 'nav_child'
        assert cat_links[0].find('a').find('span').string == 'Clustering'

    def test_strange_accept_headers(self):
        hdrs = [
            'text/plain;text/html;text/*',
            'text/html,application/xhtml+xml,application/xml;q=0.9;text/plain;q=0.8,image/png,*/*;q=0.5' ]
        for hdr in hdrs:
            # malformed headers used to return 500, just make sure they don't now
            self.app.get('/', headers=dict(Accept=hdr))

    def test_project_browse(self):
        com_cat = M.ProjectCategory.query.find(dict(label='Communications')).first()
        fax_cat = M.ProjectCategory.query.find(dict(label='Fax')).first()
        M.Project.query.find(dict(name='adobe-1')).first().category_id = com_cat._id
        response = self.app.get('/browse')
        assert len(response.html.findAll('img',{'alt':'adobe-1 Logo'})) == 1
        assert len(response.html.findAll('img',{'alt':'adobe-2 Logo'})) == 1
        response = self.app.get('/browse/communications')
        assert len(response.html.findAll('img',{'alt':'adobe-1 Logo'})) == 1
        assert len(response.html.findAll('img',{'alt':'adobe-2 Logo'})) == 0
        response = self.app.get('/browse/communications/fax')
        assert len(response.html.findAll('img',{'alt':'adobe-1 Logo'})) == 0
        assert len(response.html.findAll('img',{'alt':'adobe-2 Logo'})) == 0

    def test_neighborhood_index(self):
        response = self.app.get('/adobe/')
        projects = response.html.findAll('div',{'class':'border card'})
        assert len(projects) == 2
        assert projects[0].find('img').get('alt') == 'adobe-1 Logo'
        cat_links = response.html.find('div',{'id':'sidebar'}).findAll('ul')[0].findAll('li')
        assert len(cat_links) == 3
        assert cat_links[0].find('a').get('href') == '/adobe/browse/clustering'
        assert cat_links[0].find('a').get('class') == 'nav_child'
        assert cat_links[0].find('a').find('span').string == 'Clustering'

    def test_neighborhood_project_browse(self):
        com_cat = M.ProjectCategory.query.find(dict(label='Communications')).first()
        fax_cat = M.ProjectCategory.query.find(dict(label='Fax')).first()
        M.Project.query.find(dict(name='adobe-1')).first().category_id = com_cat._id
        M.Project.query.find(dict(name='adobe-2')).first().category_id = fax_cat._id
        response = self.app.get('/adobe/browse')
        assert len(response.html.findAll('img',{'alt':'adobe-1 Logo'})) == 1
        assert len(response.html.findAll('img',{'alt':'adobe-2 Logo'})) == 1
        response = self.app.get('/adobe/browse/communications')
        assert len(response.html.findAll('img',{'alt':'adobe-1 Logo'})) == 1
        assert len(response.html.findAll('img',{'alt':'adobe-2 Logo'})) == 1
        response = self.app.get('/adobe/browse/communications/fax')
        assert len(response.html.findAll('img',{'alt':'adobe-1 Logo'})) == 0
        assert len(response.html.findAll('img',{'alt':'adobe-2 Logo'})) == 1

    def test_markdown_to_html(self):
        r = self.app.get('/nf/markdown_to_html?markdown=*aaa*bb[Home]&project=test&app=bugs')
        assert '<p><em>aaa</em>bb<a href="/p/test/wiki/Home/">[Home]</a></p>' in r

    def test_site_css(self):
        r = self.app.get('/nf/site_style.css')
        assert(
"""a {color: #117AB4; text-decoration: none;}""" in r)
        assert(
""".active {
	color: #272727 !important;""" in r)
        assert(
"""#header h1 a {color: #454545; text-shadow: #fff 0 1px;}""" in r)
        theme = M.Theme.query.find(dict(name='forge_default')).first()
        theme.color1='#aaa'
        theme.color2='#bbb'
        theme.color3='#ccc'
        session(theme).flush()
        r = self.app.get('/nf/site_style.css')
        assert(
"""a {color: #aaa; text-decoration: none;}""" in r)
        assert(
""".active {
	color: #bbb !important;""" in r)
        assert(
"""#header h1 a {color: #ccc; text-shadow: #fff 0 1px;}""" in r)

    def test_redirect_external(self):
        r = self.app.get('/nf/redirect/?path=%s' % quote('http://google.com'))
        assert r.status_int == 302
        assert r.location == 'http://google.com'
