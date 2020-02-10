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
Model tests for project
"""
from __future__ import unicode_literals
from __future__ import absolute_import
from nose import with_setup
from nose.tools import assert_equals, assert_in
from tg import tmpl_context as c
from ming.orm.ormsession import ThreadLocalORMSession
from formencode import validators as fev

from allura import model as M
from allura.lib import helpers as h
from allura.tests import decorators as td
from alluratest.controller import setup_basic_test, setup_global_objects
from allura.lib.exceptions import ToolError, Invalid
from mock import MagicMock, patch


def setUp():
    setup_basic_test()
    setup_with_tools()


@td.with_wiki
def setup_with_tools():
    setup_global_objects()


def test_project():
    assert_equals(type(c.project.sidebar_menu()), list)
    assert_in(c.project.script_name, c.project.url())
    old_proj = c.project
    h.set_context('test/sub1', neighborhood='Projects')
    assert_equals(type(c.project.sidebar_menu()), list)
    assert_equals(type(c.project.sitemap()), list)
    assert_equals(c.project.sitemap()[1].label, 'Admin')
    assert_in(old_proj, list(c.project.parent_iter()))
    h.set_context('test', 'wiki', neighborhood='Projects')
    adobe_nbhd = M.Neighborhood.query.get(name='Adobe')
    p = M.Project.query.get(
        shortname='adobe-1', neighborhood_id=adobe_nbhd._id)
    # assert 'http' in p.url() # We moved adobe into /adobe/, not
    # http://adobe....
    assert_in(p.script_name, p.url())
    assert_equals(c.project.shortname, 'test')
    assert_in('<p>', c.project.description_html)
    c.project.uninstall_app('hello-test-mount-point')
    ThreadLocalORMSession.flush_all()

    c.project.install_app('Wiki', 'hello-test-mount-point')
    c.project.support_page = 'hello-test-mount-point'
    assert_equals(c.project.app_config('wiki').tool_name, 'wiki')
    ThreadLocalORMSession.flush_all()
    with td.raises(ToolError):
        # already installed
        c.project.install_app('Wiki', 'hello-test-mount-point')
    ThreadLocalORMSession.flush_all()
    c.project.uninstall_app('hello-test-mount-point')
    ThreadLocalORMSession.flush_all()
    with td.raises(ToolError):
        # mount point reserved
        c.project.install_app('Wiki', 'feed')
    with td.raises(ToolError):
        # mount point too long
        c.project.install_app('Wiki', 'a' * 64)
    with td.raises(ToolError):
        # mount point must begin with letter
        c.project.install_app('Wiki', '1')
    # single letter mount points are allowed
    c.project.install_app('Wiki', 'a')
    # Make sure the project support page is reset if the tool it was pointing
    # to is uninstalled.
    assert c.project.support_page == ''
    app_config = c.project.app_config('hello')
    app_inst = c.project.app_instance(app_config)
    app_inst = c.project.app_instance('hello')
    app_inst = c.project.app_instance('hello2123')
    c.project.breadcrumbs()
    c.app.config.breadcrumbs()


@with_setup(setUp)
def test_install_app_validates_options():
    from forgetracker.tracker_main import ForgeTrackerApp
    name = 'TicketMonitoringEmail'
    opt = [o for o in ForgeTrackerApp.config_options if o.name == name][0]
    opt.validator = fev.Email(not_empty=True)
    with patch.object(ForgeTrackerApp, 'config_on_install', new=[opt.name]):
        for v in [None, '', 'bad@email']:
            with td.raises(ToolError):
                c.project.install_app('Tickets', 'test-tickets', **{name: v})
            assert_equals(c.project.app_instance('test-tickets'), None)
        c.project.install_app('Tickets', 'test-tickets', **{name: 'e@e.com'})
        app = c.project.app_instance('test-tickets')
        assert_equals(app.config.options[name], 'e@e.com')


def test_project_index():
    project, idx = c.project, c.project.index()
    assert 'id' in idx
    assert idx['id'] == project.index_id()
    assert 'title' in idx
    assert 'type_s' in idx
    assert 'deleted_b' in idx
    assert 'private_b' in idx
    assert 'neighborhood_id_s' in idx
    assert 'short_description_t' in idx
    assert 'url_s' in idx


def test_subproject():
    project = M.Project.query.get(shortname='test')
    with td.raises(ToolError):
        with patch('allura.lib.plugin.ProjectRegistrationProvider') as Provider:
            Provider.get().shortname_validator.to_python.side_effect = Invalid(
                'name', 'value', {})
            # name doesn't validate
            sp = project.new_subproject('test-proj-nose')
    sp = project.new_subproject('test-proj-nose')
    spp = sp.new_subproject('spp')
    ThreadLocalORMSession.flush_all()
    sp.delete()
    ThreadLocalORMSession.flush_all()


@td.with_wiki
def test_anchored_tools():
    c.project.neighborhood.anchored_tools = 'wiki:Wiki, tickets:Ticket'
    c.project.install_app = MagicMock()
    assert_equals(c.project.sitemap()[0].label, 'Wiki')
    assert_equals(c.project.install_app.call_args[0][0], 'tickets')
    assert_equals(c.project.ordered_mounts()[0]['ac'].tool_name, 'wiki')


def test_set_ordinal_to_admin_tool():
    with h.push_config(c,
                       user=M.User.by_username('test-admin'),
                       project=M.Project.query.get(shortname='test')):
        sm = c.project.sitemap()
        assert_equals(sm[-1].tool_name, 'admin')


@with_setup(setUp)
def test_users_and_roles():
    p = M.Project.query.get(shortname='test')
    sub = p.direct_subprojects[0]
    u = M.User.by_username('test-admin')
    assert p.users_with_role('Admin') == [u]
    assert p.users_with_role('Admin') == sub.users_with_role('Admin')
    assert p.users_with_role('Admin') == p.admins()

    user = p.admins()[0]
    user.disabled = True
    ThreadLocalORMSession.flush_all()
    assert p.users_with_role('Admin') == []
    assert p.users_with_role('Admin') == p.admins()


@with_setup(setUp)
def test_project_disabled_users():
    p = M.Project.query.get(shortname='test')
    users = p.users()
    assert users[0].username == 'test-admin'
    user = M.User.by_username('test-admin')
    user.disabled = True
    ThreadLocalORMSession.flush_all()
    users = p.users()
    assert users == []

def test_screenshot_unicode_serialization():
    p = M.Project.query.get(shortname='test')
    screenshot_unicode = M.ProjectFile(project_id=p._id, category='screenshot', caption="ConSelección", filename='ConSelección.jpg')
    screenshot_ascii = M.ProjectFile(project_id=p._id, category='screenshot', caption='test-screenshot', filename='test_file.jpg')
    ThreadLocalORMSession.flush_all()

    serialized = p.__json__()
    screenshots = sorted(serialized['screenshots'], key=lambda k: k['caption'])

    assert len(screenshots) == 2
    assert screenshots[0]['url'] == 'http://localhost/p/test/screenshot/ConSelecci%C3%B3n.jpg'
    assert screenshots[0]['caption'] == "ConSelección"
    assert screenshots[0]['thumbnail_url'] == 'http://localhost/p/test/screenshot/ConSelecci%C3%B3n.jpg/thumb'

    assert screenshots[1]['url'] == 'http://localhost/p/test/screenshot/test_file.jpg'
    assert screenshots[1]['caption'] == 'test-screenshot'
    assert screenshots[1]['thumbnail_url'] == 'http://localhost/p/test/screenshot/test_file.jpg/thumb'
