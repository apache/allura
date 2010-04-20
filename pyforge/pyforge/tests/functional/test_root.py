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
        assert response.html.find('h1').string == 'All Projects'
        projects = response.html.findAll('ul',{'class':'display'})[0].findAll('li')
        assert len(projects) == 13
        assert projects[0].find('a').get('href') == '/adobe/'
        assert projects[1].find('img').get('alt') == 'adobe_1 Icon'
        cat_links = response.html.find('ul',{'id':'sidebarmenu'}).findAll('li')
        assert len(cat_links) == 4
        assert cat_links[0].find('span').get('class') == ' nav_head'
        assert cat_links[0].find('span').string == 'Categories'
        assert cat_links[1].find('a').get('href') == '/browse/clustering'
        assert cat_links[1].find('a').get('class') == 'nav_child '
        assert cat_links[1].find('a').string == 'Clustering'

    def test_project_browse(self):
        com_cat = M.ProjectCategory.query.find(dict(label='Communications')).first()
        fax_cat = M.ProjectCategory.query.find(dict(label='Fax')).first()
        M.Project.query.find(dict(name='adobe_1')).first().category_id = com_cat._id
        M.Project.query.find(dict(name='mozilla_1')).first().category_id = fax_cat._id
        response = self.app.get('/browse')
        assert len(response.html.findAll('img',{'alt':'mozilla_1 Icon'})) == 1
        assert len(response.html.findAll('img',{'alt':'adobe_1 Icon'})) == 1
        assert len(response.html.findAll('img',{'alt':'adobe_2 Icon'})) == 1
        response = self.app.get('/browse/communications')
        assert len(response.html.findAll('img',{'alt':'mozilla_1 Icon'})) == 1
        assert len(response.html.findAll('img',{'alt':'adobe_1 Icon'})) == 1
        assert len(response.html.findAll('img',{'alt':'adobe_2 Icon'})) == 0
        response = self.app.get('/browse/communications/fax')
        assert len(response.html.findAll('img',{'alt':'mozilla_1 Icon'})) == 1
        assert len(response.html.findAll('img',{'alt':'adobe_1 Icon'})) == 0
        assert len(response.html.findAll('img',{'alt':'adobe_2 Icon'})) == 0

    def test_neighborhood_index(self):
        response = self.app.get('/adobe/')
        assert response.html.find('h1').string == 'Welcome to Adobe'
        projects = response.html.findAll('ul',{'class':'display'})[0].findAll('li')
        assert len(projects) == 2
        assert projects[0].find('img').get('alt') == 'adobe_1 Icon'
        cat_links = response.html.find('ul',{'id':'sidebarmenu'}).findAll('li')
        assert len(cat_links) == 4
        assert cat_links[0].find('span').get('class') == ' nav_head'
        assert cat_links[0].find('span').string == 'Categories'
        assert cat_links[1].find('a').get('href') == '/adobe/browse/clustering'
        assert cat_links[1].find('a').get('class') == 'nav_child '
        assert cat_links[1].find('a').string == 'Clustering'

    def test_neighborhood_project_browse(self):
        com_cat = M.ProjectCategory.query.find(dict(label='Communications')).first()
        fax_cat = M.ProjectCategory.query.find(dict(label='Fax')).first()
        M.Project.query.find(dict(name='adobe_1')).first().category_id = com_cat._id
        M.Project.query.find(dict(name='adobe_2')).first().category_id = fax_cat._id
        M.Project.query.find(dict(name='mozilla_1')).first().category_id = fax_cat._id
        response = self.app.get('/adobe/browse')
        assert len(response.html.findAll('img',{'alt':'mozilla_1 Icon'})) == 0
        assert len(response.html.findAll('img',{'alt':'adobe_1 Icon'})) == 1
        assert len(response.html.findAll('img',{'alt':'adobe_2 Icon'})) == 1
        response = self.app.get('/adobe/browse/communications')
        assert len(response.html.findAll('img',{'alt':'mozilla_1 Icon'})) == 0
        assert len(response.html.findAll('img',{'alt':'adobe_1 Icon'})) == 1
        assert len(response.html.findAll('img',{'alt':'adobe_2 Icon'})) == 1
        response = self.app.get('/adobe/browse/communications/fax')
        assert len(response.html.findAll('img',{'alt':'mozilla_1 Icon'})) == 0
        assert len(response.html.findAll('img',{'alt':'adobe_1 Icon'})) == 0
        assert len(response.html.findAll('img',{'alt':'adobe_2 Icon'})) == 1

    def test_markdown_to_html(self):
        r = self.app.get('/markdown_to_html?markdown=*aaa*bb[WikiHome]&project=test&app=bugs')
        assert '<p><em>aaa</em>bb<a href="/p/test/wiki/WikiHome/">[WikiHome]</a></p>' in r

    def test_site_css(self):
        r = self.app.get('/site_style.css')
        assert("""a{
    color: #104a75;
    text-decoration: none;
}
a:visited, a:hover {color: #104a75;}
a:hover {text-decoration: underline;}
""" in r)
        assert(
"""#nav_menu_missing{
    height: 0;
    padding-top: 5px;
    border: 5px solid #aed0ea;
    border-width: 0 0 5px 0;
}""" in r)
        assert(
"""#content{
    border-style: solid;
    border-color: #D7E8F5 #aed0ea #D7E8F5 #D7E8F5;
    border-right-color: #aed0ea;
    border-width: 5px 1px 0 5px;
    width: 789px;
    min-height: 400px;
}""" in r)
        theme = M.Theme.query.find(dict(name='forge_default')).first()
        theme.color1='#aaa'
        theme.color2='#bbb'
        theme.color3='#ccc'
        session(theme).flush()
        r = self.app.get('/site_style.css')
        assert(
"""a{
    color: #aaa;
    text-decoration: none;
}
a:visited, a:hover {color: #aaa;}
""" in r)
        assert(
"""#nav_menu_missing{
    height: 0;
    padding-top: 5px;
    border: 5px solid #bbb;
    border-width: 0 0 5px 0;
}""" in r)
        assert(
"""#content{
    border-style: solid;
    border-color: #D7E8F5 #bbb #D7E8F5 #D7E8F5;
    border-right-color: #bbb;
    border-width: 5px 1px 0 5px;
    width: 789px;
    min-height: 400px;
}""" in r)
        
        

