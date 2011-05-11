# -*- coding: utf-8 -*-
"""
Model tests for project
"""
from datetime import datetime

import mock
from nose.tools import with_setup
from pylons import c, g, request
from webob import Request
from ming.orm.ormsession import ThreadLocalORMSession

from allura import model as M
from allura.lib.app_globals import Globals
from alluratest.controller import setup_basic_test, setup_global_objects


def setUp():
    setup_basic_test()
    setup_global_objects()

@with_setup(setUp)
def test_project():
    assert type(c.project.sidebar_menu()) == list
    assert c.project.script_name in c.project.url()
    old_proj = c.project
    g.set_project('test/sub1')
    assert type(c.project.sidebar_menu()) == list
    assert type(c.project.sitemap()) == list
    assert old_proj in list(c.project.parent_iter())
    g.set_project('test')
    p = M.Project.query.get(shortname='adobe-1')
    # assert 'http' in p.url() # We moved adobe into /adobe/, not http://adobe....
    assert p.script_name in p.url()
    assert c.project.shortname == 'test'
    assert '<p>' in c.project.description_html
    try:
        c.project.uninstall_app('hello-test-mount-point')
        ThreadLocalORMSession.flush_all()
    except:
        pass
    c.project.install_app('Wiki', 'hello-test-mount-point')
    c.project.support_page = 'hello-test-mount-point'
    ThreadLocalORMSession.flush_all()
    c.project.uninstall_app('hello-test-mount-point')
    ThreadLocalORMSession.flush_all()
    # Make sure the project support page is reset if the tool it was pointing
    # to is uninstalled.
    assert c.project.support_page == ''
    app_config = c.project.app_config('hello')
    app_inst = c.project.app_instance(app_config)
    app_inst = c.project.app_instance('hello')
    app_inst = c.project.app_instance('hello2123')
    c.project.render_widget(dict(
            mount_point='home',
            widget_name='welcome'))
    c.project.breadcrumbs()
    c.app.config.breadcrumbs()

def test_subproject():
    sp = c.project.new_subproject('test-project-nose')
    spp = sp.new_subproject('spp')
    ThreadLocalORMSession.flush_all()
    sp.delete()
    ThreadLocalORMSession.flush_all()

