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


class TestRootController(TestController):
    def test_index(self):
        response = self.app.get('/')
        # You can look for specific strings:
        assert_true('ProjectController' in response)
        
        #Dumb test just looks for links on the page
        links = response.html.findAll('a')
        assert_true(links, "Mummy, there are no links here!")

    def test_site_css(self):
        r = self.app.get('/site_style.css')
        assert(
"""a, a:link, a:visited, a:hover, a:active{
    color: #536BB2;
}""" in r)
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
    border-color: #EDF3FB;
    border-right-color: #aed0ea;
    border-width: 5px 1px 0 5px;
    width: 789px;
    min-height: 400px;
}""" in r)
        theme = M.Theme.query.find(dict(name='forge_default')).first()
        theme.color1='#aaa'
        theme.color2='#bbb'
        theme.color3='#ccc'
        r = self.app.get('/site_style.css')
        assert(
"""a, a:link, a:visited, a:hover, a:active{
    color: #aaa;
}""" in r)
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
    border-color: #ccc;
    border-right-color: #bbb;
    border-width: 5px 1px 0 5px;
    width: 789px;
    min-height: 400px;
}""" in r)
        
        

