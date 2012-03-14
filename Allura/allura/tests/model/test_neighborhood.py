# -*- coding: utf-8 -*-
"""
Model tests for neighborhood
"""
from nose.tools import with_setup
from pylons import c 
from ming.orm.ormsession import ThreadLocalORMSession

from allura import model as M
from allura.lib import helpers as h
from allura.tests import decorators as td
from alluratest.controller import setup_basic_test, setup_global_objects


def setUp():
    setup_basic_test()
    setup_with_tools()

@td.with_wiki
def setup_with_tools():
    setup_global_objects()

@with_setup(setUp)
def test_neighborhood():
    neighborhood_levels = ('silver', 'gold', 'platinum')
    neighborhood = M.Neighborhood.query.get(name='Projects')
    # Check css output depends of neighborhood level
    test_css = ".text{color:#000;}"
    neighborhood.css = test_css
    neighborhood.level = 'silver'
    assert neighborhood.get_custom_css() == ""
    neighborhood.level = 'gold'
    assert neighborhood.get_custom_css() == test_css
    neighborhood.level = 'platinum'
    assert neighborhood.get_custom_css() == test_css
    # Check neighborhood icon showing
    neighborhood.level = ''
    assert neighborhood.should_show_icon() is False
    for n_level in neighborhood_levels:
        neighborhood.level = n_level
        assert neighborhood.should_show_icon() is True
    # Check max projects
    neighborhood.level = ''
    assert neighborhood.get_max_projects() is None
    for n_level in neighborhood_levels:
        neighborhood.level = n_level
        assert neighborhood.get_max_projects() > 0
    neighborhood.level = 'notexists'
    assert neighborhood.get_max_projects() == 0

    # Check gold level css styles
    test_css_dict = {'barontop': u'#444',
                     'titlebarbackground': u'#555',
                     'projecttitlefont': u'arial,sans-serif',
                     'projecttitlecolor': u'#333',
                     'titlebarcolor': u'#666'}
    css_text = neighborhood.compile_css_for_gold_level(test_css_dict)
    assert '#333' in css_text
    assert '#444' in css_text
    assert '#555' in css_text
    assert '#666' in css_text
    assert 'arial,sans-serif' in css_text
    neighborhood.css = css_text
    styles_list = neighborhood.get_css_for_gold_level()
    for style in styles_list:
        assert test_css_dict[style['name']] == style['value']
