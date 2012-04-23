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
    neighborhood = M.Neighborhood.query.get(name='Projects')
    # Check css output depends of neighborhood level
    test_css = ".text{color:#000;}"
    neighborhood.css = test_css
    neighborhood.features['css'] = 'none'
    assert neighborhood.get_custom_css() == ""
    neighborhood.features['css'] = 'picker'
    assert neighborhood.get_custom_css() == test_css
    neighborhood.features['css'] = 'custom'
    assert neighborhood.get_custom_css() == test_css
    # Check max projects
    neighborhood.features['max_projects'] = None
    assert neighborhood.get_max_projects() is None
    neighborhood.features['max_projects'] = 500
    assert neighborhood.get_max_projects() == 500

    # Check picker css styles
    test_css_dict = {'barontop': u'#444',
                     'titlebarbackground': u'#555',
                     'projecttitlefont': u'arial,sans-serif',
                     'projecttitlecolor': u'#333',
                     'titlebarcolor': u'#666',
                     'addopt-icon-theme': 'dark'}
    css_text = neighborhood.compile_css_for_picker(test_css_dict)
    assert '#333' in css_text
    assert '#444' in css_text
    assert '#555' in css_text
    assert '#666' in css_text
    assert 'arial,sans-serif' in css_text
    assert 'images/neo-icon-set-ffffff-256x350.png' in css_text
    neighborhood.css = css_text
    styles_list = neighborhood.get_css_for_picker()
    for style in styles_list:
        assert test_css_dict[style['name']] == style['value']
        if style['name'] == 'titlebarcolor':
            assert '<option value="dark" selected="selected">' in style['additional']

    # Check neighborhood custom css showing
    neighborhood.features['css'] = 'none'
    assert not neighborhood.allow_custom_css
    neighborhood.features['css'] = 'picker'
    assert neighborhood.allow_custom_css
    neighborhood.features['css'] = 'custom'
    assert neighborhood.allow_custom_css
