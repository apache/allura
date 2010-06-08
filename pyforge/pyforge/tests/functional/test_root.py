# -*- coding: utf-8 -*-
"""
Functional test suite for the root controller.

This is an example of how functional tests can be written for controllers.

As opposed to a unit-test, which test a small unit of functionality,
functional tests exercise the whole application and its WSGI stack.

Please read http://pythonpaste.org/webtest/ for more information.

"""
from nose.tools import assert_true

from pyforge.tests import TestController
from pyforge import model as M
from ming.orm import session

class TestRootController(TestController):
    def test_index(self):
        response = self.app.get('/')
        assert response.html.find('h1',{'class':'title'}).string == 'All Projects'
        projects = response.html.findAll('ul',{'class':'display'})[0].findAll('li')
        assert len(projects) == 10, len(projects)
        assert projects[0].find('a').get('href') == '/adobe/'
        assert projects[1].find('img').get('alt') == 'adobe-1 Logo'
        cat_links = response.html.find('div',{'id':'sidebar'}).findAll('li')
        assert len(cat_links) == 3
        assert cat_links[0].find('a').get('href') == '/browse/clustering'
        assert cat_links[0].find('a').get('class') == 'nav_child'
        assert cat_links[0].find('a').find('span').string == 'Clustering'

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
        cat_links = response.html.find('div',{'id':'sidebar'}).findAll('li')
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
        r = self.app.get('/nf/markdown_to_html?markdown=*aaa*bb[WikiHome]&project=test&app=bugs')
        assert '<p><em>aaa</em>bb<a href="/p/test/wiki/WikiHome/">[WikiHome]</a></p>' in r

    def test_site_css(self):
        r = self.app.get('/nf/site_style.css')
        assert(
"""a {color: #295d78; text-decoration: none;}""" in r)
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
        
        

