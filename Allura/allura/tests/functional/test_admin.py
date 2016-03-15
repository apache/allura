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

import re
import os
import allura
import pkg_resources
import StringIO
from contextlib import contextmanager
import logging

import tg
import PIL
from nose.tools import assert_equals, assert_in, assert_not_in, assert_is_not_none, assert_greater
from ming.orm.ormsession import ThreadLocalORMSession
from tg import expose
from pylons import tmpl_context as c, app_globals as g
import mock

from allura.tests import TestController
from allura.tests import decorators as td
from allura.tests.decorators import audits, out_audits
from alluratest.controller import TestRestApiBase, setup_trove_categories
from allura import model as M
from allura.app import SitemapEntry
from allura.lib.plugin import AdminExtension
from allura.lib import helpers as h
from allura.ext.admin.admin_main import AdminApp

from forgewiki.wiki_main import ForgeWikiApp


log = logging.getLogger(__name__)


class TestProjectAdmin(TestController):

    def test_admin_controller(self):
        self.app.get('/admin/')
        with audits(
                'change summary to Milkshakes are for crazy monkeys',
                'change project name to My Test Project',
                u'change short description to (\u00bf A Test Project \?){45}'):
            self.app.post('/admin/update', params=dict(
                name='My Test Project',
                shortname='test',
                summary='Milkshakes are for crazy monkeys',
                short_description=u'\u00bf A Test Project ?'.encode(
                        'utf-8') * 45,
                labels='aaa,bbb'))
        r = self.app.get('/admin/overview')
        assert 'A Test Project ?\xc2\xbf A' in r
        assert 'Test Subproject' not in r
        assert 'Milkshakes are for crazy monkeys' in r
        sidebar = r.html.find(id='sidebar')
        assert sidebar.find('a', href='/p/test/admin/overview'), sidebar

        # Add a subproject
        with audits('create subproject test-subproject'):
            self.app.post('/admin/update_mounts', params={
                'new.install': 'install',
                'new.ep_name': '',
                'new.ordinal': '1',
                'new.mount_point': 'test-subproject',
                'new.mount_label': 'Test Subproject'})
        r = self.app.get('/admin/overview')
        assert 'Test Subproject' in r
        # Rename a subproject
        with audits('update subproject test/test-subproject'):
            self.app.post('/admin/update_mounts', params={
                'subproject-0.shortname': 'test/test-subproject',
                'subproject-0.name': 'Tst Sbprj',
                'subproject-0.ordinal': '100',
            })
        r = self.app.get('/admin/overview')
        assert 'Tst Sbprj' in r
        # Remove a subproject
        with audits('delete subproject test/test-subproject'):
            self.app.post('/admin/update_mounts', params={
                'subproject-0.delete': 'on',
                'subproject-0.shortname': 'test/test-subproject',
                'new.ep_name': '',
            })

        # Add a tool
        with audits('install tool test-tool'):
            r = self.app.post('/admin/update_mounts', params={
                'new.install': 'install',
                'new.ep_name': 'Wiki',
                'new.ordinal': '1',
                'new.mount_point': 'test-tool',
                'new.mount_label': 'Test Tool'})
        assert 'error' not in self.webflash(r)
        # check tool in the nav
        r = self.app.get('/p/test/test-tool/').follow()
        active_link = r.html.findAll('li', {'class': 'selected'})
        assert_equals(len(active_link), 1)
        assert active_link[0].contents[1]['href'] == '/p/test/test-tool/'
        with audits('install tool test-tool2'):
            r = self.app.post('/admin/update_mounts', params={
                'new.install': 'install',
                'new.ep_name': 'Wiki',
                'new.ordinal': '1',
                'new.mount_point': 'test-tool2',
                'new.mount_label': 'Test Tool2'})
        assert 'error' not in self.webflash(r)
        # check the nav - tools of same type are grouped
        r = self.app.get('/p/test/test-tool/Home/')
        active_link = r.html.findAll('li', {'class': 'selected'})
        assert len(active_link) == 2
        assert active_link[0].contents[1]['href'] == '/p/test/_list/wiki'
        assert r.html.findAll('a', {'href': '/p/test/test-tool2/'})
        assert r.html.findAll('a', {'href': '/p/test/test-tool/'})

        # check can't create dup tool
        r = self.app.post('/admin/update_mounts', params={
            'new.install': 'install',
            'new.ep_name': 'Wiki',
            'new.ordinal': '1',
            'new.mount_point': 'test-tool',
            'new.mount_label': 'Test Tool'})
        assert 'error' in self.webflash(r)
        # Rename a tool
        with audits('update tool test-tool'):
            self.app.post('/admin/update_mounts', params={
                'tool-0.mount_point': 'test-tool',
                'tool-0.mount_label': 'Tst Tuul',
                'tool-0.ordinal': '200',
            })
        r = self.app.get('/admin/overview')
        assert 'Tst Tuul' in r
        # Remove a tool
        with audits('uninstall tool test-tool'):
            self.app.post('/admin/update_mounts', params={
                'tool-0.delete': 'on',
                'tool-0.mount_point': 'test-tool',
                'new.ep_name': '',
            })

        # Check the audit log
        r = self.app.get('/admin/audit/')
        assert "uninstall tool test-tool" in r.body, r.body

        # Make sure several 'project_menu_updated' events got sent
        menu_updated_events = M.MonQTask.query.find({
            'task_name': 'allura.tasks.event_tasks.event',
            'args': 'project_menu_updated'
        }).all()
        assert_equals(len(menu_updated_events), 7)

    def test_features(self):
        proj = M.Project.query.get(shortname='test')
        assert_equals(proj.features, [])
        with audits(u"change project features to \[u'One', u'Two'\]"):
            self.app.post('/admin/update', params={
                'features-0.feature': 'One',
                'features-1.feature': '  ',
                'features-2.feature': ' Two '})
        r = self.app.get('/admin/overview')
        features = r.html.find('div', {'id': 'features'})
        features = features.findAll('input', {'type': 'text'})
        # two features + extra empty input + stub hidden input for js
        assert_equals(len(features), 2+1+1)
        assert_equals(features[0]['value'], u'One')
        assert_equals(features[1]['value'], u'Two')
        proj = M.Project.query.get(shortname='test')
        assert_equals(proj.features, [u'One', u'Two'])

    def test_admin_export_control(self):
        self.app.get('/admin/')
        with audits('change project export controlled status to True'):
            self.app.post('/admin/update', params=dict(
                shortname='test',
                export_controlled='True'))
        with out_audits('change project export controlled status to True'):
            self.app.post('/admin/update', params=dict(
                shortname='test',
                summary='TL;DR',
                export_controlled='True'))
        with audits('change project export controlled status to False'):
            self.app.post('/admin/update', params=dict(
                shortname='test',
                export_controlled='False'))

    @td.with_wiki
    def test_block_user_empty_data(self):
        r = self.app.post('/admin/wiki/block_user',
                          params={'username': '', 'perm': '', 'reason': ''})
        assert_equals(r.json, dict(error='Enter username'))

    @td.with_wiki
    def test_unblock_user_empty_data(self):
        r = self.app.post('/admin/wiki/unblock_user',
                          params={'user_id': '', 'perm': ''})
        assert_equals(r.json, dict(error='Select user to unblock'))

    @td.with_wiki
    def test_block_user(self):
        r = self.app.get('/admin/wiki/permissions')
        assert '<input type="checkbox" name="user_id"' not in r

        user = M.User.by_username('test-admin')
        r = self.app.post('/admin/wiki/block_user',
                          params={'username': 'test-admin', 'perm': 'read', 'reason': 'Comment'})
        assert_equals(
            r.json, dict(user_id=str(user._id), username='test-admin', reason='Comment'))
        user = M.User.by_username('test-admin')
        admin_role = M.ProjectRole.by_user(user)
        app = M.Project.query.get(shortname='test').app_instance('wiki')
        ace = M.ACL.contains(M.ACE.deny(admin_role._id, 'read'), app.acl)
        assert_equals(ace.reason, 'Comment')
        r = self.app.get('/admin/wiki/permissions')
        assert '<input type="checkbox" name="user_id" value="%s">test-admin (Comment)' % user._id in r

    @td.with_wiki
    def test_unblock_user(self):
        r = self.app.post('/admin/wiki/block_user',
                          params={'username': 'test-admin', 'perm': 'read'})
        user = M.User.by_username('test-admin')
        admin_role = M.ProjectRole.by_user(user)
        app = M.Project.query.get(shortname='test').app_instance('wiki')
        ace = M.ACE.deny(admin_role._id, 'read')
        r = self.app.get('/admin/wiki/permissions')
        assert '<input type="checkbox" name="user_id" value="%s">test-admin' % user._id in r
        app = M.Project.query.get(shortname='test').app_instance('wiki')
        assert M.ACL.contains(ace, app.acl) is not None
        r = self.app.post('/admin/wiki/unblock_user',
                          params={'user_id': str(user._id), 'perm': 'read'})
        assert_equals(r.json, dict(unblocked=[str(user._id)]))
        assert M.ACL.contains(ace, app.acl) is None
        r = self.app.get('/admin/wiki/permissions')
        assert '<input type="checkbox" name="user_id"' not in r

    @td.with_wiki
    def test_block_unblock_multiple_users(self):
        self.app.post('/admin/wiki/block_user',
                      params={'username': 'test-admin', 'perm': 'read', 'reason': 'Spammer'})
        self.app.post('/admin/wiki/block_user',
                      params={'username': 'test-user', 'perm': 'read'})
        admin = M.User.by_username('test-admin')
        user = M.User.by_username('test-user')
        admin_role = M.ProjectRole.by_user(admin)
        user_role = M.ProjectRole.by_user(user)
        app = M.Project.query.get(shortname='test').app_instance('wiki')
        deny_admin = M.ACE.deny(admin_role._id, 'read')
        deny_user = M.ACE.deny(user_role._id, 'read')
        assert M.ACL.contains(deny_admin, app.acl) is not None
        assert M.ACL.contains(deny_user, app.acl) is not None
        r = self.app.get('/admin/wiki/permissions')
        assert '<input type="checkbox" name="user_id" value="%s">test-admin (Spammer)' % admin._id in r
        assert '<input type="checkbox" name="user_id" value="%s">test-user' % user._id in r

        self.app.post('/admin/wiki/unblock_user',
                      params={'user_id': str(user._id), 'perm': 'read'})
        self.app.post('/admin/wiki/unblock_user',
                      params={'user_id': str(admin._id), 'perm': 'read'})
        app = M.Project.query.get(shortname='test').app_instance('wiki')
        assert M.ACL.contains(deny_admin, app.acl) is None
        assert M.ACL.contains(deny_user, app.acl) is None
        r = self.app.get('/admin/wiki/permissions')
        assert '<input type="checkbox" name="user_id"' not in r

    @td.with_wiki
    def test_blocked_users_remains_after_saving_all_permissions(self):
        self.app.post('/admin/wiki/block_user',
                      params={'username': 'test-user', 'perm': 'read', 'reason': 'Comment'})
        self.app.post('/admin/wiki/block_user',
                      params={'username': 'test-user', 'perm': 'post', 'reason': 'Comment'})
        user = M.User.by_username('test-user')
        user_role = M.ProjectRole.by_user(user)
        app = M.Project.query.get(shortname='test').app_instance('wiki')
        assert M.ACL.contains(M.ACE.deny(user_role._id, 'read'), app.acl)
        assert M.ACL.contains(M.ACE.deny(user_role._id, 'post'), app.acl)
        old_acl = app.acl

        permissions_page = self.app.get('/admin/wiki/permissions')
        permissions_page.forms[0].submit()

        # deny ACEs for user still should be there
        app = M.Project.query.get(shortname='test').app_instance('wiki')
        assert M.ACL.contains(M.ACE.deny(user_role._id, 'read'), app.acl)
        assert M.ACL.contains(M.ACE.deny(user_role._id, 'post'), app.acl)
        # ...and all old ACEs also
        for ace in old_acl:
            assert_in(ace, app.acl)

    def test_tool_permissions(self):
        BUILTIN_APPS = ['activity', 'blog', 'discussion', 'git', 'link',
                        'shorturl', 'svn', 'tickets', 'userstats', 'wiki']
        self.app.get('/admin/')
        project = M.Project.query.get(shortname='test')
        for i, ep in enumerate(pkg_resources.iter_entry_points('allura')):
            App = ep.load()
            tool = ep.name
            cfg = M.AppConfig(
                project_id=project._id,
                tool_name=tool,
                options={'mount_point': '', 'mount_label': ''})
            app = App(project, cfg)
            if not app.installable or ep.name.lower() not in BUILTIN_APPS:
                continue
            with audits('install tool test-%d' % i):
                self.app.post('/admin/update_mounts', params={
                    'new.install': 'install',
                    'new.ep_name': tool,
                    'new.ordinal': str(i),
                    'new.mount_point': 'test-%d' % i,
                    'new.mount_label': tool})
            r = self.app.get('/admin/test-%d/permissions' % i)
            cards = [
                tag for tag in r.html.findAll('input')
                if (
                    tag.get('type') == 'hidden' and
                    tag.get('name') and
                    tag['name'].startswith('card-') and
                    tag['name'].endswith('.id'))]
            assert len(cards) == len(app.permissions), cards

    def test_tool_installation_limit(self):
        with mock.patch.object(ForgeWikiApp, 'max_instances') as mi:
            mi.__get__ = mock.Mock(return_value=1)

            c.user = M.User.query.get(username='root')
            c.project = M.Project.query.get(shortname='test')
            data = c.project.nav_data(admin_options=True)
            menu = [tool['text'] for tool in data['installable_tools']]
            assert_in('Wiki', menu)

            r = self.app.post('/p/test/admin/update_mounts/', params={
                'new.install': 'install',
                'new.ep_name': 'Wiki',
                'new.ordinal': '1',
                'new.mount_point': 'wiki',
                'new.mount_label': 'Wiki'})

            c.project = M.Project.query.get(shortname='test')
            data = c.project.nav_data(admin_options=True)
            menu = [tool['text'] for tool in data['installable_tools']]
            assert_not_in('Wiki', menu)

            r = self.app.post('/p/test/admin/update_mounts/', params={
                'new.install': 'install',
                'new.ep_name': 'Wiki',
                'new.ordinal': '1',
                'new.mount_point': 'wiki2',
                'new.mount_label': 'Wiki 2'})

            assert 'error' in self.webflash(r)
            assert 'limit exceeded' in self.webflash(r)

    def test_install_tool_form(self):
        r = self.app.get('/admin/install_tool?tool_name=wiki')
        assert_in(u'Installing Wiki', r)

    def test_install_tool_form_options(self):
        opts = ['AllowEmailPosting']
        with mock.patch.object(ForgeWikiApp, 'config_on_install', new=opts):
            r = self.app.get('/admin/install_tool?tool_name=wiki')
            assert_in(u'<input id="AllowEmailPosting" name="AllowEmailPosting"', r)

    def test_install_tool_form_subproject(self):
        r = self.app.get('/admin/install_tool?tool_name=subproject')
        assert_in(u'Installing Sub Project', r)

    def test_project_icon(self):
        file_name = 'neo-icon-set-454545-256x350.png'
        file_path = os.path.join(
            allura.__path__[0], 'nf', 'allura', 'images', file_name)
        file_data = file(file_path).read()
        upload = ('icon', file_name, file_data)

        self.app.get('/admin/')
        with audits('update project icon'):
            self.app.post('/admin/update', params=dict(
                name='Test Project',
                shortname='test',
                short_description='A Test Project'),
                upload_files=[upload])
        r = self.app.get('/p/test/icon')
        image = PIL.Image.open(StringIO.StringIO(r.body))
        assert image.size == (48, 48)

        r = self.app.get('/p/test/icon?foo=bar')

    def test_project_screenshot(self):
        file_name = 'neo-icon-set-454545-256x350.png'
        file_path = os.path.join(
            allura.__path__[0], 'nf', 'allura', 'images', file_name)
        file_data = file(file_path).read()
        upload = ('screenshot', file_name, file_data)

        self.app.get('/admin/')
        with audits('add screenshot'):
            self.app.post('/admin/add_screenshot', params=dict(
                caption='test me'),
                upload_files=[upload])
        p_nbhd = M.Neighborhood.query.get(name='Projects')
        project = M.Project.query.get(
            shortname='test', neighborhood_id=p_nbhd._id)
        filename = project.get_screenshots()[0].filename
        r = self.app.get('/p/test/screenshot/' + filename)
        uploaded = PIL.Image.open(file_path)
        screenshot = PIL.Image.open(StringIO.StringIO(r.body))
        assert uploaded.size == screenshot.size
        r = self.app.get('/p/test/screenshot/' + filename + '/thumb')
        thumb = PIL.Image.open(StringIO.StringIO(r.body))
        assert thumb.size == (150, 150)
        # FIX: home pages don't currently support screenshots (now that they're a wiki);
        # reinstate this code (or appropriate) when we have a macro for that
        #r = self.app.get('/p/test/home/')
        #assert '/p/test/screenshot/'+filename in r
        #assert 'test me' in r
        # test edit
        req = self.app.get('/admin/screenshots')
        req.forms[0]['caption'].value = 'aaa'
        req.forms[0].submit()
        #r = self.app.get('/p/test/home/')
        #assert 'aaa' in r
        # test delete
        req = self.app.get('/admin/screenshots')
        req.forms[1].submit()
        #r = self.app.get('/p/test/home/')
        #assert 'aaa' not in r

    def test_sort_screenshots(self):
        for file_name in ('admin_24.png', 'admin_32.png'):
            file_path = os.path.join(allura.__path__[0], 'nf', 'allura',
                                     'images', file_name)
            file_data = file(file_path).read()
            upload = ('screenshot', file_name, file_data)
            self.app.post('/admin/add_screenshot', params=dict(
                caption=file_name),
                upload_files=[upload])

        p_nbhd = M.Neighborhood.query.get(name='Projects')
        project = M.Project.query.get(shortname='test',
                                      neighborhood_id=p_nbhd._id)
        # first uploaded is first by default
        screenshots = project.get_screenshots()
        assert_equals(screenshots[0].filename, 'admin_24.png')
        # reverse order
        params = dict((str(ss._id), len(screenshots) - 1 - i)
                      for i, ss in enumerate(screenshots))
        self.app.post('/admin/sort_screenshots', params)
        assert_equals(project.get_screenshots()[0].filename, 'admin_32.png')

    def test_project_delete_undelete(self):
        # create a subproject
        with audits('create subproject sub-del-undel'):
            self.app.post('/admin/update_mounts', params={
                'new.install': 'install',
                'new.ep_name': '',
                'new.ordinal': '1',
                'new.mount_point': 'sub-del-undel',
                'new.mount_label': 'sub-del-undel'})
        r = self.app.get('/p/test/admin/overview')
        assert 'This project has been deleted and is not visible to non-admin users' not in r
        assert r.html.find(
            'input', {'name': 'removal', 'value': ''}).has_key('checked')
        assert not r.html.find(
            'input', {'name': 'removal', 'value': 'deleted'}).has_key('checked')
        with audits('delete project'):
            self.app.post('/admin/update', params=dict(
                name='Test Project',
                shortname='test',
                removal='deleted',
                short_description='A Test Project',
                delete='on'))
        r = self.app.get('/p/test/admin/overview')
        assert 'This project has been deleted and is not visible to non-admin users' in r
        assert not r.html.find(
            'input', {'name': 'removal', 'value': ''}).has_key('checked')
        assert r.html.find(
            'input', {'name': 'removal', 'value': 'deleted'}).has_key('checked')
        # make sure subprojects get deleted too
        r = self.app.get('/p/test/sub-del-undel/admin/overview')
        assert 'This project has been deleted and is not visible to non-admin users' in r
        with audits('undelete project'):
            self.app.post('/admin/update', params=dict(
                name='Test Project',
                shortname='test',
                removal='',
                short_description='A Test Project',
                undelete='on'))
        r = self.app.get('/p/test/admin/overview')
        assert 'This project has been deleted and is not visible to non-admin users' not in r
        assert r.html.find(
            'input', {'name': 'removal', 'value': ''}).has_key('checked')
        assert not r.html.find(
            'input', {'name': 'removal', 'value': 'deleted'}).has_key('checked')

    def test_project_delete_not_allowed(self):
        # turn off project delete option
        from allura.ext.admin.admin_main import config
        old_allow_project_delete = config.get('allow_project_delete', ())
        config['allow_project_delete'] = False
        try:
            # create a subproject
            with audits('create subproject sub-no-del'):
                self.app.post('/admin/update_mounts', params={
                    'new.install': 'install',
                    'new.ep_name': '',
                    'new.ordinal': '1',
                    'new.mount_point': 'sub-no-del',
                    'new.mount_label': 'sub-no-del'})
            # root project doesn't have delete option
            r = self.app.get('/p/test/admin/overview')
            assert not r.html.find(
                'input', {'name': 'removal', 'value': 'deleted'})
            # subprojects can still be deleted
            r = self.app.get('/p/test/sub-no-del/admin/overview')
            assert r.html.find(
                'input', {'name': 'removal', 'value': 'deleted'})
            # attempt to delete root project won't do anything
            self.app.post('/admin/update', params=dict(
                name='Test Project',
                shortname='test',
                removal='deleted',
                short_description='A Test Project',
                delete='on'))
            r = self.app.get('/p/test/admin/overview')
            assert 'This project has been deleted and is not visible to non-admin users' not in r
            # make sure subproject delete works
            with audits(
                    'change project removal status to deleted',
                    'delete project'):
                self.app.post('/p/test/sub-no-del/admin/update', params=dict(
                    name='sub1',
                    shortname='sub1',
                    removal='deleted',
                    short_description='A Test Project',
                    delete='on'))
            r = self.app.get('/p/test/sub-no-del/admin/overview')
            assert 'This project has been deleted and is not visible to non-admin users' in r
            assert r.html.find(
                'input', {'name': 'removal', 'value': 'deleted'}).has_key('checked')
        finally:
            if old_allow_project_delete == ():
                del config['allow_project_delete']
            else:
                config['allow_project_delete'] = old_allow_project_delete

    def test_add_remove_trove_cat(self):
        setup_trove_categories()

        r = self.app.get('/admin/trove')
        assert 'No Database Environment categories have been selected.' in r
        assert '<span class="trove_fullpath">Database Environment :: Database API</span>' not in r
        # add a cat
        with audits('add trove root_database: Database Environment :: Database API'):
            form = r.forms['add_trove_root_database']
            form['new_trove'].value = '506'
            r = form.submit().follow()
        # make sure it worked
        assert 'No Database Environment categories have been selected.' not in r
        assert '<span class="trove_fullpath">Database Environment :: Database API :: Python Database API</span>' in r
        # delete the cat
        with audits('remove trove root_database: Database Environment :: Database API'):
            r = r.forms['delete_trove_root_database_506'].submit().follow()
        # make sure it worked
        assert 'No Database Environment categories have been selected.' in r
        assert '<span class="trove_fullpath">Database Environment :: Database API :: Python Database API</span>' not in r

    def test_add_remove_label(self):
        setup_trove_categories()

        r = self.app.get('/admin/trove')
        form = r.forms['label_edit_form']
        form['labels'].value = 'foo,bar,baz'
        with audits('updated labels'):
            r = form.submit()
        r = r.follow()
        p_nbhd = M.Neighborhood.query.get(name='Projects')
        p = M.Project.query.get(shortname='test', neighborhood_id=p_nbhd._id)
        assert p.labels == ['foo', 'bar', 'baz']
        assert form['labels'].value == 'foo,bar,baz'
        ThreadLocalORMSession.close_all()
        form['labels'].value = 'asdf'
        with audits('updated labels'):
            r = form.submit()
        r = r.follow()
        p = M.Project.query.get(shortname='test', neighborhood_id=p_nbhd._id)
        assert_equals(p.labels, ['asdf'])
        assert form['labels'].value == 'asdf'

    @td.with_wiki
    def test_log_permission(self):
        r = self.app.get('/admin/wiki/permissions')
        select = r.html.find('select', {'name': 'card-0.new'})
        opt_admin = select.find(text='Admin').parent
        opt_developer = select.find(text='Developer').parent
        assert opt_admin.name == 'option'
        assert opt_developer.name == 'option'

        with audits('updated "admin" permission: "Admin" => "Admin, Developer" for wiki'):
            self.app.post('/admin/wiki/update', params={
                'card-0.new': opt_developer['value'],
                'card-0.value': opt_admin['value'],
                'card-0.id': 'admin'})

        with audits('updated "admin" permission: "Admin, Developer" => "Admin" for wiki'):
            self.app.post('/admin/wiki/update', params={
                'card-0.value': opt_admin['value'],
                'card-0.id': 'admin'})

    def test_project_permissions(self):
        r = self.app.get('/admin/permissions/')
        assert len(r.html.findAll('input', {'name': 'card-0.value'})) == 1
        select = r.html.find('select', {'name': 'card-0.new'})
        opt_admin = select.find(text='Admin').parent
        opt_developer = select.find(text='Developer').parent
        assert opt_admin.name == 'option'
        assert opt_developer.name == 'option'
        with audits('updated "admin" permissions: "Admin" => "Admin,Developer"'):
            r = self.app.post('/admin/permissions/update', params={
                'card-0.new': opt_developer['value'],
                'card-0.value': opt_admin['value'],
                'card-0.id': 'admin'})
        r = self.app.get('/admin/permissions/')
        assigned_ids = [t['value']
                        for t in r.html.findAll('input', {'name': 'card-0.value'})]
        assert len(assigned_ids) == 2
        assert opt_developer['value'] in assigned_ids
        assert opt_admin['value'] in assigned_ids

    def test_subproject_permissions(self):
        with audits('create subproject test-subproject'):
            self.app.post('/admin/update_mounts', params={
                'new.install': 'install',
                'new.ep_name': '',
                'new.ordinal': '1',
                'new.mount_point': 'test-subproject',
                'new.mount_label': 'Test Subproject'})
        r = self.app.get('/test-subproject/admin/permissions/')
        assert len(r.html.findAll('input', {'name': 'card-0.value'})) == 0
        select = r.html.find('select', {'name': 'card-0.new'})
        opt_admin = select.find(text='Admin').parent
        opt_developer = select.find(text='Developer').parent
        assert opt_admin.name == 'option'
        assert opt_developer.name == 'option'
        with audits('updated "admin" permissions: "" => "Admin,Developer"'):
            r = self.app.post('/test-subproject/admin/permissions/update', params={
                'card-0.new': opt_developer['value'],
                'card-0.value': opt_admin['value'],
                'card-0.id': 'admin'})
        r = self.app.get('/test-subproject/admin/permissions/')
        assigned_ids = [t['value']
                        for t in r.html.findAll('input', {'name': 'card-0.value'})]
        assert len(assigned_ids) == 2
        assert opt_developer['value'] in assigned_ids
        assert opt_admin['value'] in assigned_ids

    def test_project_groups(self):
        r = self.app.get('/admin/groups/')
        dev_holder = r.html.find(
            'table', {'id': 'usergroup_admin'}).findAll('tr')[2]
        developer_id = dev_holder['data-group']
        with audits('add user test-user to Developer'):
            r = self.app.post('/admin/groups/add_user', params={
                'role_id': developer_id,
                'username': 'test-user'})
        r = self.app.get('/admin/groups/')
        dev_holder = r.html.find(
            'table', {'id': 'usergroup_admin'}).findAll('tr')[2]
        users = dev_holder.find('ul', {'class': 'users'}).findAll(
            'li', {'class': 'deleter'})
        assert 'test-user' in users[0]['data-user']
        # Make sure we can open role page for builtin role
        r = self.app.get('/admin/groups/' + developer_id +
                         '/', validate_chunk=True)

    def test_new_admin_subscriptions(self):
        """Newly added admin must be subscribed to all the tools in the project"""
        r = self.app.get('/admin/groups/')
        admin_holder = r.html.find(
            'table', {'id': 'usergroup_admin'}).findAll('tr')[1]
        admin_id = admin_holder['data-group']
        with audits('add user test-user to Admin'):
            self.app.post('/admin/groups/add_user', params={
                'role_id': admin_id,
                'username': 'test-user'})
        p_nbhd = M.Neighborhood.query.get(name='Projects')
        p = M.Project.query.get(shortname='test', neighborhood_id=p_nbhd._id)
        uid = M.User.by_username('test-user')._id
        for ac in p.app_configs:
            sub = M.Mailbox.subscribed(
                user_id=uid, project_id=p._id, app_config_id=ac._id)
            assert sub, 'New admin not subscribed to app %s' % ac

    def test_new_user_subscriptions(self):
        """Newly added user must not be subscribed to all the tools in the project if he is not admin"""
        r = self.app.get('/admin/groups/')
        dev_holder = r.html.find(
            'table', {'id': 'usergroup_admin'}).findAll('tr')[2]
        developer_id = dev_holder['data-group']
        with audits('add user test-user to Developer'):
            self.app.post('/admin/groups/add_user', params={
                'role_id': developer_id,
                'username': 'test-user'})
        p_nbhd = M.Neighborhood.query.get(name='Projects')
        p = M.Project.query.get(shortname='test', neighborhood_id=p_nbhd._id)
        uid = M.User.by_username('test-user')._id
        for ac in p.app_configs:
            sub = M.Mailbox.subscribed(
                user_id=uid, project_id=p._id, app_config_id=ac._id)
            assert not sub, 'New user subscribed to app %s' % ac

    def test_subroles(self):
        """Make sure subroles are preserved during group updates."""
        def check_roles(r):
            dev_holder = r.html.find(
                'table', {'id': 'usergroup_admin'}).findAll('tr')[2]
            mem_holder = r.html.find(
                'table', {'id': 'usergroup_admin'}).findAll('tr')[3]
            assert 'All users in Admin group' in str(dev_holder)
            assert 'All users in Developer group' in str(mem_holder)

        r = self.app.get('/admin/groups/')

        admin_holder = r.html.find(
            'table', {'id': 'usergroup_admin'}).findAll('tr')[1]
        admin_id = admin_holder['data-group']
        # test that subroles are intact after user added
        with audits('add user test-user to Admin'):
            r = self.app.post('/admin/groups/add_user', params={
                'role_id': admin_id,
                'username': 'test-user'})
        r = self.app.get('/admin/groups/')
        check_roles(r)
        # test that subroles are intact after user deleted
        with audits('remove user test-user from Admin'):
            r = self.app.post('/admin/groups/remove_user', params={
                'role_id': admin_id,
                'username': 'test-user'})
        r = self.app.get('/admin/groups/')
        check_roles(r)

    def test_cannot_remove_all_admins(self):
        """Must always have at least one user with the Admin role (and anon
        doesn't count)."""
        r = self.app.get('/admin/groups/')
        admin_holder = r.html.find(
            'table', {'id': 'usergroup_admin'}).findAll('tr')[1]
        admin_id = admin_holder['data-group']
        users = admin_holder.find('ul', {'class': 'users'}).findAll(
            'li', {'class': 'deleter'})
        assert len(users) == 1
        r = self.app.post('/admin/groups/remove_user', params={
            'role_id': admin_id,
            'username': 'admin1'})
        assert r.json[
            'error'] == 'You must have at least one user with the Admin role.'
        r = self.app.get('/admin/groups/')
        admin_holder = r.html.find(
            'table', {'id': 'usergroup_admin'}).findAll('tr')[1]
        users = admin_holder.find('ul', {'class': 'users'}).findAll(
            'li', {'class': 'deleter'})
        assert len(users) == 1

    def test_cannot_add_anon_to_group(self):
        r = self.app.get('/admin/groups/')
        dev_holder = r.html.find(
            'table', {'id': 'usergroup_admin'}).findAll('tr')[2]
        developer_id = dev_holder['data-group']
        r = self.app.post('/admin/groups/add_user', params={
            'role_id': developer_id,
            'username': ''})
        assert r.json['error'] == 'You must choose a user to add.'
        r = self.app.get('/admin/groups/')
        dev_holder = r.html.find(
            'table', {'id': 'usergroup_admin'}).findAll('tr')[2]
        users = dev_holder.find('ul', {'class': 'users'}).findAll(
            'li', {'class': 'deleter'})
        # no user was added
        assert len(users) == 0
        assert M.ProjectRole.query.find(dict(
            name='*anonymous', user_id=None,
            roles={'$ne': []})).count() == 0

    def test_project_multi_groups(self):
        r = self.app.get('/admin/groups/')
        user_id = M.User.by_username('test-admin')._id
        admin_holder = r.html.find(
            'table', {'id': 'usergroup_admin'}).findAll('tr')[1]
        admin_id = admin_holder['data-group']
        with audits('add user test-user to Admin'):
            r = self.app.post('/admin/groups/add_user', params={
                'role_id': admin_id,
                'username': 'test-user'})
            assert 'error' not in r.json
        r = self.app.post('/admin/groups/add_user', params={
            'role_id': admin_id,
            'username': 'test-user'})
        assert r.json[
            'error'] == 'Test User (test-user) is already in the group Admin.'
        r = self.app.get('/admin/groups/')
        assert 'test-user' in str(r), r.showbrowser()
        with audits('remove user test-user from Admin'):
            r = self.app.post('/admin/groups/remove_user', params={
                'role_id': admin_id,
                'username': 'test-user'})
        r = self.app.get('/admin/groups/')
        assert 'test-user' not in str(r), r.showbrowser()

    @td.with_wiki
    def test_new_group(self):
        r = self.app.get('/admin/groups/new', validate_chunk=True)
        with audits('create group Developer'):
            r = self.app.post('/admin/groups/create',
                              params={'name': 'Developer'})
        assert 'error' in self.webflash(r)
        with audits('create group RoleNew1'):
            r = self.app.post('/admin/groups/create',
                              params={'name': 'RoleNew1'})
        r = self.app.get('/admin/groups/')
        role_holder = r.html.find(
            'table', {'id': 'usergroup_admin'}).findAll('tr')[4]
        assert 'RoleNew1' in str(role_holder)
        role_id = role_holder['data-group']
        r = self.app.get('/admin/groups/' + role_id + '/', validate_chunk=True)
        r = self.app.post('/admin/groups/'
                          + str(role_id) + '/update', params={'_id': role_id, 'name': 'Developer'})
        assert 'error' in self.webflash(r)
        assert 'already exists' in self.webflash(r)

        with audits('update group name RoleNew1=>rleNew2'):
            r = self.app.post('/admin/groups/' + str(role_id) + '/update',
                              params={'_id': role_id, 'name': 'rleNew2'}).follow()
        assert 'RoleNew1' not in r
        assert 'rleNew2' in r

        # add test-user to role
        role_holder = r.html.find(
            'table', {'id': 'usergroup_admin'}).findAll('tr')[4]
        rleNew2_id = role_holder['data-group']
        with audits('add user test-user to rleNew2'):
            r = self.app.post('/admin/groups/add_user', params={
                'role_id': rleNew2_id,
                'username': 'test-user'})

        with audits('delete group rleNew2'):
            r = self.app.post('/admin/groups/delete_group', params={
                'group_name': 'rleNew2'})
        assert 'deleted' in self.webflash(r)
        r = self.app.get('/admin/groups/', status=200)
        roles = [str(t) for t in r.html.findAll('td', {'class': 'group'})]
        assert 'RoleNew1' not in roles
        assert 'rleNew2' not in roles

        # make sure can still access homepage after one of user's roles were
        # deleted
        r = self.app.get('/p/test/wiki/',
                         extra_environ=dict(username='test-user')).follow()
        assert r.status == '200 OK'

    def test_change_perms(self):
        r = self.app.get('/admin/groups/')
        dev_holder = r.html.find(
            'table', {'id': 'usergroup_admin'}).findAll('tr')[2]
        mem_holder = r.html.find(
            'table', {'id': 'usergroup_admin'}).findAll('tr')[3]
        mem_id = mem_holder['data-group']
        # neither group has update permission
        assert dev_holder.findAll('ul')[1].findAll('li')[2]['class'] == "no"
        assert mem_holder.findAll('ul')[1].findAll('li')[2]['class'] == "no"
        # add update permission to Member
        r = self.app.post('/admin/groups/change_perm', params={
            'role_id': mem_id,
            'permission': 'create',
            'allow': 'true'})
        r = self.app.get('/admin/groups/')
        dev_holder = r.html.find(
            'table', {'id': 'usergroup_admin'}).findAll('tr')[2]
        mem_holder = r.html.find(
            'table', {'id': 'usergroup_admin'}).findAll('tr')[3]
        # Member now has update permission
        assert mem_holder.findAll('ul')[1].findAll('li')[2]['class'] == "yes"
        # Developer has inherited update permission from Member
        assert dev_holder.findAll('ul')[1].findAll(
            'li')[2]['class'] == "inherit"
        # remove update permission from Member
        r = self.app.post('/admin/groups/change_perm', params={
            'role_id': mem_id,
            'permission': 'create',
            'allow': 'false'})
        r = self.app.get('/admin/groups/')
        dev_holder = r.html.find(
            'table', {'id': 'usergroup_admin'}).findAll('tr')[2]
        mem_holder = r.html.find(
            'table', {'id': 'usergroup_admin'}).findAll('tr')[3]
        # neither group has update permission
        assert dev_holder.findAll('ul')[1].findAll('li')[2]['class'] == "no"
        assert mem_holder.findAll('ul')[1].findAll('li')[2]['class'] == "no"

    def test_permission_inherit(self):
        r = self.app.get('/admin/groups/')
        admin_holder = r.html.find(
            'table', {'id': 'usergroup_admin'}).findAll('tr')[1]
        admin_id = admin_holder['data-group']
        mem_holder = r.html.find(
            'table', {'id': 'usergroup_admin'}).findAll('tr')[3]
        mem_id = mem_holder['data-group']
        anon_holder = r.html.find(
            'table', {'id': 'usergroup_admin'}).findAll('tr')[5]
        anon_id = anon_holder['data-group']
        # first remove create from Admin so we can see it inherit
        r = self.app.post('/admin/groups/change_perm', params={
            'role_id': admin_id,
            'permission': 'create',
            'allow': 'false'})
        # updates to anon inherit up
        r = self.app.post('/admin/groups/change_perm', params={
            'role_id': anon_id,
            'permission': 'create',
            'allow': 'true'})
        assert {u'text': u'Inherited permission create from Anonymous',
                u'has': u'inherit', u'name': u'create'} in r.json[admin_id]
        assert {u'text': u'Inherited permission create from Anonymous',
                u'has': u'inherit', u'name': u'create'} in r.json[mem_id]
        assert {u'text': u'Has permission create', u'has':
                u'yes', u'name': u'create'} in r.json[anon_id]
        r = self.app.post('/admin/groups/change_perm', params={
            'role_id': anon_id,
            'permission': 'create',
            'allow': 'false'})
        assert {u'text': u'Does not have permission create',
                u'has': u'no', u'name': u'create'} in r.json[admin_id]
        assert {u'text': u'Does not have permission create',
                u'has': u'no', u'name': u'create'} in r.json[mem_id]
        assert {u'text': u'Does not have permission create',
                u'has': u'no', u'name': u'create'} in r.json[anon_id]
        # updates to Member inherit up
        r = self.app.post('/admin/groups/change_perm', params={
            'role_id': mem_id,
            'permission': 'create',
            'allow': 'true'})
        assert {u'text': u'Inherited permission create from Member',
                u'has': u'inherit', u'name': u'create'} in r.json[admin_id]
        assert {u'text': u'Has permission create', u'has':
                u'yes', u'name': u'create'} in r.json[mem_id]
        assert {u'text': u'Does not have permission create',
                u'has': u'no', u'name': u'create'} in r.json[anon_id]
        r = self.app.post('/admin/groups/change_perm', params={
            'role_id': mem_id,
            'permission': 'create',
            'allow': 'false'})
        assert {u'text': u'Does not have permission create',
                u'has': u'no', u'name': u'create'} in r.json[admin_id]
        assert {u'text': u'Does not have permission create',
                u'has': u'no', u'name': u'create'} in r.json[mem_id]
        assert {u'text': u'Does not have permission create',
                u'has': u'no', u'name': u'create'} in r.json[anon_id]

    def test_admin_extension_sidebar(self):

        class FooSettingsController(object):

            @expose()
            def index(self, *a, **kw):
                return 'here the foo settings go'

        class FooSettingsExtension(AdminExtension):

            def update_project_sidebar_menu(self, sidebar_links):
                base_url = c.project.url() + 'admin/ext/'
                sidebar_links.append(
                    SitemapEntry('Foo Settings', base_url + 'foo'))

            @property
            def project_admin_controllers(self):
                return {
                    'foo': FooSettingsController,
                }

        eps = {
            'admin': {
                'foo-settings': FooSettingsExtension,
            }
        }

        with mock.patch.dict(g.entry_points, eps):
            main_page = self.app.get('/admin/')
            foo_page = main_page.click(description='Foo Settings')
            url = foo_page.environ['PATH_INFO']
            assert url.endswith('/admin/ext/foo'), url
            assert_equals('here the foo settings go', foo_page.body)


class TestExport(TestController):

    def setUp(self):
        super(TestExport, self).setUp()
        self.setup_with_tools()

    @td.with_wiki
    @td.with_tool('test', 'Wiki', 'wiki2', 'Wiki2')
    def setup_with_tools(self):
        pass

    def test_exportable_tools_for(self):
        project = M.Project.query.get(shortname='test')
        exportable_tools = AdminApp.exportable_tools_for(project)
        exportable_mount_points = [
            t.options.mount_point for t in exportable_tools]
        assert_equals(exportable_mount_points, [u'admin', u'wiki', u'wiki2'])

    def test_access(self):
        r = self.app.get('/admin/export',
                         extra_environ={'username': '*anonymous'}).follow()
        assert_equals(r.request.url,
                      'http://localhost/auth/?return_to=%2Fadmin%2Fexport')
        self.app.get('/admin/export',
                     extra_environ={'username': 'test-user'},
                     status=403)
        r = self.app.post('/admin/export',
                          extra_environ={'username': '*anonymous'}).follow()
        assert_equals(r.request.url, 'http://localhost/auth/')
        self.app.post('/admin/export',
                      extra_environ={'username': 'test-user'},
                      status=403)

    def test_ini_option(self):
        tg.config['bulk_export_enabled'] = 'false'
        r = self.app.get('/admin/')
        assert_not_in('Export', r)
        r = self.app.get('/admin/export', status=404)
        tg.config['bulk_export_enabled'] = 'true'
        r = self.app.get('/admin/')
        assert_in('Export', r)


    @mock.patch('allura.model.session.project_doc_session')
    def test_export_page_contains_exportable_tools(self, session):
        session.return_value = {'result': [{"total_size": 10000}]}

        r = self.app.get('/admin/export')
        assert_in('Wiki</label> <a href="/p/test/wiki/">/p/test/wiki/</a>', r)
        assert_in(
            'Wiki2</label> <a href="/p/test/wiki2/">/p/test/wiki2/</a>', r)
        assert_not_in(
            'Search</label> <a href="/p/test/search/">/p/test/search/</a>', r)

    def test_export_page_contains_hidden_tools(self):
        with mock.patch('allura.ext.search.search_main.SearchApp.exportable'):
            project = M.Project.query.get(shortname='test')
            exportable_tools = AdminApp.exportable_tools_for(project)
            exportable_mount_points = [
                t.options.mount_point for t in exportable_tools]
            assert_equals(exportable_mount_points,
                          [u'admin', u'search', u'wiki', u'wiki2'])

    def test_tools_not_selected(self):
        r = self.app.post('/admin/export')
        assert_in('error', self.webflash(r))

    def test_bad_tool(self):
        r = self.app.post('/admin/export', {'tools': u'search'})
        assert_in('error', self.webflash(r))

    @mock.patch('allura.ext.admin.admin_main.export_tasks')
    def test_selected_one_tool(self, export_tasks):
        r = self.app.post('/admin/export', {'tools': u'wiki'})
        assert_in('ok', self.webflash(r))
        export_tasks.bulk_export.post.assert_called_once_with(
            [u'wiki'], 'test.zip', send_email=True, with_attachments=False)

    @mock.patch('allura.ext.admin.admin_main.export_tasks')
    def test_selected_multiple_tools(self, export_tasks):
        r = self.app.post('/admin/export', {'tools': [u'wiki', u'wiki2']})
        assert_in('ok', self.webflash(r))
        export_tasks.bulk_export.post.assert_called_once_with(
            [u'wiki', u'wiki2'], 'test.zip', send_email=True, with_attachments=False)

    @mock.patch('allura.model.session.project_doc_session')
    def test_export_in_progress(self, session):
        from allura.tasks import export_tasks
        session.return_value = {'result': [{"total_size": 10000}]}
        export_tasks.bulk_export.post(['wiki'])
        r = self.app.get('/admin/export')
        assert_in('<h2>Busy</h2>', r.body)

    @td.with_user_project('test-user')
    def test_bulk_export_path_for_user_project(self):
        project = M.Project.query.get(shortname='u/test-user')
        assert_equals(project.bulk_export_path(),
                      '/tmp/bulk_export/u/test-user')

    @td.with_user_project('test-user')
    def test_bulk_export_filename_for_user_project(self):
        project = M.Project.query.get(shortname='u/test-user')
        assert_equals(project.bulk_export_filename(), 'test-user.zip')

    def test_bulk_export_filename_for_nbhd(self):
        project = M.Project.query.get(name='Home Project for Projects')
        assert_equals(project.bulk_export_filename(), 'p.zip')

    def test_bulk_export_path_for_nbhd(self):
        project = M.Project.query.get(name='Home Project for Projects')
        assert_equals(project.bulk_export_path(), '/tmp/bulk_export/p/p')

    @mock.patch('allura.model.session.project_doc_session')
    def test_export_page_contains_check_all_checkbox(self, session):
        session.return_value = {'result': [{"total_size": 10000}]}

        r = self.app.get('/admin/export')
        assert_in('<input type="checkbox" id="check-all">', r)
        assert_in('Check All</label>', r)


class TestRestExport(TestRestApiBase):

    @mock.patch('allura.model.project.MonQTask')
    def test_export_status(self, MonQTask):
        MonQTask.query.get.return_value = None
        r = self.api_get('/rest/p/test/admin/export_status')
        assert_equals(r.json, {'status': 'ready'})

        MonQTask.query.get.return_value = 'something'
        r = self.api_get('/rest/p/test/admin/export_status')
        assert_equals(r.json, {'status': 'busy'})

    @mock.patch('allura.model.project.MonQTask')
    @mock.patch('allura.ext.admin.admin_main.AdminApp.exportable_tools_for')
    @mock.patch('allura.ext.admin.admin_main.export_tasks.bulk_export')
    def test_export_no_exportable_tools(self, bulk_export, exportable_tools, MonQTask):
        MonQTask.query.get.return_value = None
        exportable_tools.return_value = []
        r = self.api_post('/rest/p/test/admin/export',
                          tools='tickets, discussion', status=400)
        assert_equals(bulk_export.post.call_count, 0)

    @mock.patch('allura.model.project.MonQTask')
    @mock.patch('allura.ext.admin.admin_main.AdminApp.exportable_tools_for')
    @mock.patch('allura.ext.admin.admin_main.export_tasks.bulk_export')
    def test_export_no_tools_specified(self, bulk_export, exportable_tools, MonQTask):
        MonQTask.query.get.return_value = None
        exportable_tools.return_value = [
            mock.Mock(options=mock.Mock(mount_point='tickets')),
            mock.Mock(options=mock.Mock(mount_point='discussion')),
        ]
        r = self.api_post('/rest/p/test/admin/export', status=400)
        assert_equals(bulk_export.post.call_count, 0)

    @mock.patch('allura.model.project.MonQTask')
    @mock.patch('allura.ext.admin.admin_main.AdminApp.exportable_tools_for')
    @mock.patch('allura.ext.admin.admin_main.export_tasks.bulk_export')
    def test_export_busy(self, bulk_export, exportable_tools, MonQTask):
        MonQTask.query.get.return_value = 'something'
        exportable_tools.return_value = [
            mock.Mock(options=mock.Mock(mount_point='tickets')),
            mock.Mock(options=mock.Mock(mount_point='discussion')),
        ]
        r = self.api_post('/rest/p/test/admin/export',
                          tools='tickets, discussion', status=503)
        assert_equals(bulk_export.post.call_count, 0)

    @mock.patch('allura.model.project.MonQTask')
    @mock.patch('allura.ext.admin.admin_main.AdminApp.exportable_tools_for')
    @mock.patch('allura.ext.admin.admin_main.export_tasks.bulk_export')
    def test_export_ok(self, bulk_export, exportable_tools, MonQTask):
        MonQTask.query.get.return_value = None
        exportable_tools.return_value = [
            mock.Mock(options=mock.Mock(mount_point='tickets')),
            mock.Mock(options=mock.Mock(mount_point='discussion')),
        ]
        r = self.api_post('/rest/p/test/admin/export',
                          tools='tickets, discussion', status=200)
        assert_equals(r.json, {
            'filename': 'test.zip',
            'status': 'in progress',
        })
        bulk_export.post.assert_called_once_with(
            ['tickets', 'discussion'], 'test.zip', send_email=False, with_attachments=False)


class TestRestInstallTool(TestRestApiBase):

    def test_missing_mount_info(self):
        r = self.api_get('/rest/p/test/')
        tools_names = [t['name'] for t in r.json['tools']]
        assert 'tickets' not in tools_names

        data = {
            'tool': 'tickets'
        }
        r = self.api_post('/rest/p/test/admin/install_tool/', **data)
        assert_equals(r.json['success'], False)
        assert_equals(r.json['info'], 'All arguments required.')

    def test_invalid_tool(self):
        r = self.api_get('/rest/p/test/')
        tools_names = [t['name'] for t in r.json['tools']]
        assert 'tickets' not in tools_names

        data = {
            'tool': 'something',
            'mount_point': 'ticketsmount1',
            'mount_label': 'tickets_label1'
        }
        r = self.api_post('/rest/p/test/admin/install_tool/', **data)
        assert_equals(r.json['success'], False)
        assert_equals(r.json['info'],
                      'Incorrect tool name, or limit is reached.')

    def test_bad_mount(self):
        r = self.api_get('/rest/p/test/')
        tools_names = [t['name'] for t in r.json['tools']]
        assert 'tickets' not in tools_names

        data = {
            'tool': 'tickets',
            'mount_point': 'tickets_mount1',
            'mount_label': 'tickets_label1'
        }
        r = self.api_post('/rest/p/test/admin/install_tool/', **data)
        assert_equals(r.json['success'], False)
        assert_equals(r.json['info'],
                      'Mount point "tickets_mount1" is invalid')

    def test_install_tool_ok(self):
        r = self.api_get('/rest/p/test/')
        tools_names = [t['name'] for t in r.json['tools']]
        assert 'tickets' not in tools_names

        data = {
            'tool': 'tickets',
            'mount_point': 'ticketsmount1',
            'mount_label': 'tickets_label1'
        }
        r = self.api_post('/rest/p/test/admin/install_tool/', **data)
        assert_equals(r.json['success'], True)
        assert_equals(r.json['info'],
                      'Tool %s with mount_point %s and mount_label %s was created.'
                      % ('tickets', 'ticketsmount1', 'tickets_label1'))

        project = M.Project.query.get(shortname='test')
        assert_equals(project.ordered_mounts()
                      [-1]['ac'].options.mount_point, 'ticketsmount1')
        audit_log = M.AuditLog.query.find(
            {'project_id': project._id}).sort('_id', -1).first()
        assert_equals(audit_log.message, 'install tool ticketsmount1')

    def test_tool_exists(self):
        with mock.patch.object(ForgeWikiApp, 'max_instances') as mi:
            mi.__get__ = mock.Mock(return_value=2)
            r = self.api_get('/rest/p/test/')
            tools_names = [t['name'] for t in r.json['tools']]
            assert 'wiki' not in tools_names

            data = {
                'tool': 'wiki',
                'mount_point': 'wikimount1',
                'mount_label': 'wiki_label1'
            }
            project = M.Project.query.get(shortname='test')
            with h.push_config(c, user=M.User.query.get()):
                project.install_app('wiki', mount_point=data['mount_point'])
            r = self.api_post('/rest/p/test/admin/install_tool/', **data)
            assert_equals(r.json['success'], False)
            assert_equals(r.json['info'], 'Mount point already exists.')

    def test_tool_installation_limit(self):
        with mock.patch.object(ForgeWikiApp, 'max_instances') as mi:
            mi.__get__ = mock.Mock(return_value=1)
            r = self.api_get('/rest/p/test/')
            tools_names = [t['name'] for t in r.json['tools']]
            assert 'wiki' not in tools_names

            data = {
                'tool': 'wiki',
                'mount_point': 'wikimount',
                'mount_label': 'wiki_label'
            }
            r = self.api_post('/rest/p/test/admin/install_tool/', **data)
            assert_equals(r.json['success'], True)

            data['mount_point'] = 'wikimount1'
            data['mount_label'] = 'wiki_label1'
            r = self.api_post('/rest/p/test/admin/install_tool/', **data)
            assert_equals(r.json['success'], False)
            assert_equals(r.json['info'],
                          'Incorrect tool name, or limit is reached.')

    def test_unauthorized(self):
        r = self.api_get('/rest/p/test/')
        tools_names = [t['name'] for t in r.json['tools']]
        assert 'tickets' not in tools_names

        data = {
            'tool': 'wiki',
            'mount_point': 'wikimount1',
            'mount_label': 'wiki_label1'
        }
        r = self.app.post('/rest/p/test/admin/install_tool/',
                          extra_environ={'username': '*anonymous'},
                          status=401,
                          params=data)
        assert_equals(r.status, '401 Unauthorized')

    def test_order(self):
        def get_labels():
            project = M.Project.query.get(shortname='test')
            labels = []
            for mount in project.ordered_mounts(include_hidden=True):
                if 'ac' in mount:
                    labels.append(mount['ac'].options.mount_label)
                elif 'sub' in mount:
                    labels.append(mount['sub'].name)
            return labels
        assert_equals(get_labels(),
                      ['Admin', 'Search', 'Activity', 'A Subproject'])

        data = [
            {
                'tool': 'tickets',
                'mount_point': 'ticketsmount1',
                'mount_label': 'ta',
            },
            {
                'tool': 'tickets',
                'mount_point': 'ticketsmount2',
                'mount_label': 'tc',
                'order': 'last'
            },
            {
                'tool': 'tickets',
                'mount_point': 'ticketsmount3',
                'mount_label': 'tb',
                'order': 'alpha_tool'
            },
            {
                'tool': 'tickets',
                'mount_point': 'ticketsmount4',
                'mount_label': 't1',
                'order': 'first'
            },
        ]
        for datum in data:
            r = self.api_post('/rest/p/test/admin/install_tool/', **datum)
            assert_equals(r.json['success'], True)
            assert_equals(r.json['info'],
                          'Tool %s with mount_point %s and mount_label %s was created.'
                          % (datum['tool'], datum['mount_point'], datum['mount_label']))

        assert_equals(
            get_labels(), ['t1', 'Admin', 'Search', 'Activity', 'A Subproject', 'ta', 'tb', 'tc'])


class TestRestAdminOptions(TestRestApiBase):
    def test_no_mount_point(self):
        r = self.api_get('/rest/p/test/admin/admin_options/')
        assert_equals(r.status, '400 Bad Request')
        assert_in('Must provide a mount point', r.body)

    def test_invalid_mount_point(self):
        r = self.api_get('/rest/p/test/admin/admin_options/?mount_point=asdf')
        assert_equals(r.status, '400 Bad Request')
        assert_in('The mount point you provided was invalid', r.body)

    @td.with_tool('test', 'Git', 'git')
    def test_valid_mount_point(self):
        r = self.api_get('/rest/p/test/admin/admin_options/?mount_point=git')
        assert_equals(r.status, '200 OK')
        assert_is_not_none(r.json['options'])


class TestRestMountOrder(TestRestApiBase):
    def test_no_kw(self):
        r = self.api_post('/rest/p/test/admin/mount_order/')
        assert_equals(r.status, '400 Bad Request')
        assert_in('Expected kw params in the form of "ordinal: mount_point"', r.body)

    def test_invalid_kw(self):
        data = {'1': 'git', 'two': 'admin'}
        r = self.api_post('/rest/p/test/admin/mount_order/', **data)
        assert_equals(r.status, '400 Bad Request')
        assert_in('Invalid kw: expected "ordinal: mount_point"', r.body)

    @td.with_wiki
    def test_reorder(self):
        d1 = {
            '0': u'sub1',
            '1': u'wiki',
            '2': u'admin'
        }
        d2 = {
            '0': u'wiki',
            '1': u'sub1',
            '2': u'admin'
        }

        tool = {
            u'icon': u'tool-admin',
            u'is_anchored': False,
            u'mount_point': u'sub1',
            u'name': u'A Subproject',
            u'tool_name': u'sub',
            u'url': u'/p/test/sub1/'
        }

        # Set initial order to d1
        r = self.api_post('/rest/p/test/admin/mount_order/', **d1)
        assert_equals(r.json['status'], 'ok')

        # Get index of sub1
        a = self.api_get('/p/test/_nav.json').json['menu'].index(tool)

        # Set order to d2
        r = self.api_post('/rest/p/test/admin/mount_order/', **d2)
        assert_equals(r.json['status'], 'ok')

        # Get index of sub1 after reordering
        b = self.api_get('/p/test/_nav.json').json['menu'].index(tool)

        assert_greater(b, a)


class TestRestToolGrouping(TestRestApiBase):
    def test_invalid_grouping_threshold(self):
        for invalid_value in ('100', 'asdf'):
            r = self.api_post('/rest/p/test/admin/configure_tool_grouping/', grouping_threshold=invalid_value)
            assert_equals(r.status, '400 Bad Request')
            assert_in('Invalid threshold. Expected a value between 1 and 10', r.body)

    @td.with_wiki
    @td.with_tool('test', 'Wiki', 'wiki2')
    @td.with_tool('test', 'Wiki', 'wiki3')
    def test_valid_grouping_threshold(self):
        # Set threshold to 2
        r = self.api_post('/rest/p/test/admin/configure_tool_grouping/', grouping_threshold='2')
        assert_equals(r.status, '200 OK')

        # The 'wiki' mount_point should not exist at the top level
        result1 = self.app.get('/p/test/_nav.json')
        assert_not_in('wiki', [tool['mount_point'] for tool in result1.json['menu']])

        # Set threshold to 3
        r = self.api_post('/rest/p/test/admin/configure_tool_grouping/', grouping_threshold='3')
        assert_equals(r.status, '200 OK')

        # The wiki mount_point should now be at the top level of the menu
        result2 = self.app.get('/p/test/_nav.json')
        assert_in('wiki', [tool['mount_point'] for tool in result2.json['menu']])


class TestInstallableTools(TestRestApiBase):
    def test_installable_tools_response(self):
        r = self.api_get('/rest/p/test/admin/installable_tools')
        assert_equals(r.status, '200 OK')
        assert_in('External Link', [tool['tool_label'] for tool in r.json['tools']])
