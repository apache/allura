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

from pyforge import model as M
from pyforge.lib.app_globals import Globals
from pyforge.tests import helpers

def setUp():
    helpers.setup_basic_test()
    helpers.setup_global_objects()

def test_search_config():
    "just make sure needs_commit doesn't throw an exception"
    assert M.SearchConfig.query.find().count() == 1
    cfg = M.SearchConfig.query.find().one()
    cfg.needs_commit()

def test_scheduled_messages():
    sm = M.ScheduledMessage(_id=None, when=datetime.utcnow(), exchange='audit', routing_key='test.none')
    ThreadLocalORMSession.flush_all()
    M.ScheduledMessage.fire_when_ready()

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
    c.project.roles
    try:
        c.project.uninstall_app('hello-test-mount-point')
        ThreadLocalORMSession.flush_all()
    except:
        pass
    c.project.install_app('hello_forge', 'hello-test-mount-point')
    ThreadLocalORMSession.flush_all()
    c.project.uninstall_app('hello-test-mount-point')
    ThreadLocalORMSession.flush_all()
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

