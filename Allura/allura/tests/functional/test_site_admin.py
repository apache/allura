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

import json
import datetime as dt
import bson

from mock import patch, MagicMock
from ming.odm import ThreadLocalORMSession
from tg import tmpl_context as c
from tg import config
from bson import ObjectId

from allura import model as M
from allura.tests import TestController
from allura.tests import decorators as td
from allura.lib import helpers as h
from allura.lib.decorators import task
from allura.lib.plugin import LocalAuthenticationProvider


class TestSiteAdmin(TestController):

    def test_access(self):
        r = self.app.get('/nf/admin/', extra_environ=dict(
            username='test-user'), status=403)

        r = self.app.get('/nf/admin/', extra_environ=dict(
            username='*anonymous'), status=302)
        r = r.follow()
        assert 'Login' in r

    def test_home(self):
        r = self.app.get('/nf/admin/', extra_environ=dict(
            username='root'))
        assert 'Site Admin Home' in r

    def test_stats(self):
        r = self.app.get('/nf/admin/stats/', extra_environ=dict(
            username='root'))
        assert 'Forge Site Admin' in r.html.find(
            'h2', {'class': 'dark title'}).find('span').contents[0]
        stats_table = r.html.find('table')
        cells = stats_table.findAll('td')
        assert cells[0].contents[0] == 'Adobe', cells[0].contents[0]

    def test_tickets_access(self):
        self.app.get('/nf/admin/api_tickets', extra_environ=dict(
            username='test-user'), status=403)

    def test_new_projects_access(self):
        self.app.get('/nf/admin/new_projects', extra_environ=dict(
            username='test_user'), status=403)
        r = self.app.get('/nf/admin/new_projects', extra_environ=dict(
            username='*anonymous'), status=302).follow()
        assert 'Login' in r

    def test_new_projects(self):
        r = self.app.get('/nf/admin/new_projects', extra_environ=dict(
            username='root'))
        headers = r.html.find('table').findAll('th')
        assert headers[1].contents[0] == 'Created'
        assert headers[2].contents[0] == 'Shortname'
        assert headers[3].contents[0] == 'Name'
        assert headers[4].contents[0] == 'Short description'
        assert headers[5].contents[0] == 'Summary'
        assert headers[6].contents[0] == 'Homepage'
        assert headers[7].contents[0] == 'Admins'

    def test_new_projects_deleted_projects(self):
        '''Deleted projects should not be visible here'''
        r = self.app.get('/nf/admin/new_projects', extra_environ=dict(
            username='root'))
        count = len(r.html.find('table').findAll('tr'))
        p = M.Project.query.get(shortname='test')
        p.deleted = True
        ThreadLocalORMSession.flush_all()
        r = self.app.get('/nf/admin/new_projects', extra_environ=dict(
            username='root'))
        assert len(r.html.find('table').findAll('tr')) == count - 1

    def test_new_projects_daterange_filtering(self):
        r = self.app.get('/nf/admin/new_projects', extra_environ=dict(
            username='root'))
        count = len(r.html.find('table').findAll('tr'))
        assert count == 7

        filtr = r.forms[0]
        filtr['start-dt'] = '2000/01/01 10:10:10'
        filtr['end-dt'] = '2000/01/01 09:09:09'
        r = filtr.submit()
        count = len(r.html.find('table').findAll('tr'))
        assert count == 1  # only row with headers - no results

    def test_reclone_repo_access(self):
        r = self.app.get('/nf/admin/reclone_repo', extra_environ=dict(
            username='*anonymous'), status=302).follow()
        assert 'Login' in r

    def test_reclone_repo(self):
        r = self.app.get('/nf/admin/reclone_repo')
        assert 'Reclone repository' in r

    def test_reclone_repo_default_value(self):
        r = self.app.get('/nf/admin/reclone_repo')
        assert 'value="p"' in r

    def test_task_list(self):
        r = self.app.get('/nf/admin/task_manager',
                         extra_environ=dict(username='*anonymous'), status=302)
        import math
        M.MonQTask.post(math.ceil, (12.5,))
        r = self.app.get('/nf/admin/task_manager?page_num=1')
        assert 'math.ceil' in r, r

    def test_task_view(self):
        import re
        task = M.MonQTask.post(re.search, ('pattern', 'string'), {'flags': re.I})
        url = '/nf/admin/task_manager/view/%s' % task._id
        r = self.app.get(
            url, extra_environ=dict(username='*anonymous'), status=302)
        r = self.app.get(url)
        assert 'regex.regex.search' in r, r
        assert '<td>pattern</td>' in r, r
        assert '<td>string</td>' in r, r
        assert '<th class="second-column-headers side-header">flags</th>' in r, r
        assert f'<td>{re.I}</td>' in r, r
        assert 'ready' in r, r

        # test resubmit too
        M.MonQTask.run_ready()
        r = self.app.get(url)
        assert 'complete' in r, r
        r = r.forms['resubmit-task-form'].submit()
        r = r.follow()
        assert 'ready' in r, r

    def test_task_new(self):
        r = self.app.get('/nf/admin/task_manager/new')
        assert 'New Task' in r, r

    def test_task_create(self):
        project = M.Project.query.get(shortname='test')
        app = project.app_instance('admin')
        user = M.User.by_username('root')

        task_args = dict(
            args=['foo'],
            kwargs=dict(bar='baz'))

        r = self.app.post('/nf/admin/task_manager/create', params=dict(
            task='allura.tests.functional.test_site_admin.test_task',
            task_args=json.dumps(task_args),
            user='root',
            path='/p/test/admin',
        ), status=302)
        task = next(M.MonQTask.query.find({}).sort('_id', -1))
        assert str(task._id) in r.location
        assert task.context['project_id'] == project._id
        assert task.context['app_config_id'] == app.config._id
        assert task.context['user_id'] == user._id
        assert task.args == task_args['args']
        assert task.kwargs == task_args['kwargs']

    def test_task_doc(self):
        r = self.app.get('/nf/admin/task_manager/task_doc', params=dict(
            task_name='allura.tests.functional.test_site_admin.test_task'))
        assert json.loads(r.text)['doc'] == 'test_task doc string'


class TestSiteAdminNotifications(TestController):

    def test_site_notifications_access(self):
        self.app.get('/nf/admin/site_notifications', extra_environ=dict(
            username='test_user'), status=403)
        r = self.app.get('/nf/admin/site_notifications', extra_environ=dict(
            username='*anonymous'), status=302).follow()
        assert 'Login' in r

    def test_site_notifications(self):
        M.notification.SiteNotification(active=True,
                                        impressions=0,
                                        content='test1',
                                        user_role='test2',
                                        page_regex='test3',
                                        page_tool_type='test4')
        ThreadLocalORMSession().flush_all()
        assert M.notification.SiteNotification.query.find().count() == 1

        r = self.app.get('/nf/admin/site_notifications/', extra_environ=dict(
            username='root'))
        table = r.html.find('table')
        headers = table.findAll('th')
        row = table.findAll('td')

        assert headers[0].contents[0] == 'Active'
        assert headers[1].contents[0] == 'Impressions'
        assert headers[2].contents[0] == 'Content'
        assert headers[3].contents[0] == 'User Role'
        assert headers[4].contents[0] == 'Page Regex'
        assert headers[5].contents[0] == 'Page Type'

        assert row[0].contents[0].contents[0] == 'True'
        assert row[1].contents[0].contents[0] == '0'
        assert row[2].contents[0].contents[0] == 'test1'
        assert row[3].contents[0].contents[0] == 'test2'
        assert row[4].contents[0].contents[0] == 'test3'
        assert row[5].contents[0].contents[0] == 'test4'

    def test_site_notification_new_template(self):
        r = self.app.get('/nf/admin/site_notifications/new')

        assert r
        assert 'New Site Notification' in r
        assert 'Active' in r
        assert 'Impressions' in r
        assert 'Content' in r
        assert 'User Role' in r
        assert 'Page Regex' in r
        assert 'Page Type' in r

    def test_site_notification_create(self):
        count = M.notification.SiteNotification.query.find().count()
        active = 'True'
        impressions = '7'
        content = 'test1'
        user_role = 'test2'
        page_regex = 'test3'
        page_tool_type = 'test4'
        r = self.app.post('/nf/admin/site_notifications/create', params=dict(
            active=active,
            impressions=impressions,
            content=content,
            user_role=user_role,
            page_regex=page_regex,
            page_tool_type=page_tool_type))
        note = next(M.notification.SiteNotification.query.find().sort('_id', -1))

        assert '/nf/admin/site_notifications' in r.location

        assert M.notification.SiteNotification.query.find().count() == count + 1

        assert note.active == bool('True')
        assert note.impressions == int(impressions)
        assert note.content == content
        assert note.user_role == user_role
        assert note.page_regex == page_regex
        assert note.page_tool_type == page_tool_type

    def test_site_notification_edit_template(self):
        note = M.notification.SiteNotification(active=True,
                                               impressions=0,
                                               content='test1',
                                               user_role='test2',
                                               page_regex='test3',
                                               page_tool_type='test4')
        ThreadLocalORMSession().flush_all()
        r = self.app.get(f'/nf/admin/site_notifications/{note._id}/edit')

        assert r
        assert 'checked' in r.form['active'].attrs
        assert r.form['impressions'].value == '0'
        assert r.form['content'].value == 'test1'
        assert r.form['user_role'].value == 'test2'
        assert r.form['page_regex'].value == 'test3'
        assert r.form['page_tool_type'].value == 'test4'

        assert 'Edit Site Notification' in r
        assert 'Active' in r
        assert 'Impressions' in r
        assert 'Content' in r
        assert 'User Role' in r
        assert 'Page Regex' in r
        assert 'Page Type' in r

    def test_site_notification_update(self):
        active = 'True'
        impressions = '7'
        content = 'test1'
        user_role = 'test2'
        page_regex = 'test3'
        page_tool_type = 'test4'

        note = M.notification.SiteNotification(active=False,
                                               impressions=0,
                                               content='test')
        ThreadLocalORMSession().flush_all()

        count = M.notification.SiteNotification.query.find().count()

        r = self.app.post(f'/nf/admin/site_notifications/{note._id}/update', params=dict(
            active=active,
            impressions=impressions,
            content=content,
            user_role=user_role,
            page_regex=page_regex,
            page_tool_type=page_tool_type))
        ThreadLocalORMSession().flush_all()

        note = next(M.notification.SiteNotification.query.find().sort('_id', -1))

        assert '/nf/admin/site_notifications' in r.location
        assert M.notification.SiteNotification.query.find().count() == count
        assert note.active == bool('True')
        assert note.impressions == int(impressions)
        assert note.content == content
        assert note.user_role == user_role
        assert note.page_regex == page_regex
        assert note.page_tool_type == page_tool_type

    def test_site_notification_delete(self):
        note = M.notification.SiteNotification(active=False,
                                               impressions=0,
                                               content='test')
        ThreadLocalORMSession().flush_all()

        count = M.notification.SiteNotification.query.find().count()

        self.app.post(f'/nf/admin/site_notifications/{note._id}/delete')
        assert M.notification.SiteNotification.query.find().count() == count -1
        assert M.notification.SiteNotification.query.get(_id=bson.ObjectId(note._id)) is None


class TestProjectsSearch(TestController):

    TEST_HIT = MagicMock(hits=1, docs=[{
        'name_s': 'Test Project',
        'is_nbhd_project_b': False,
        'is_root_b': True,
        'title': ['Project Test Project'],
        'deleted_b': False,
        'shortname_s': 'test',
        'private_b': False,
        'url_s': 'http://localhost:8080/p/test/',
        'neighborhood_id_s': '53ccf6e6100d2b0741746c66',
        'removal_changed_date_dt': '2014-07-21T11:18:00.087Z',
        'registration_dt': '2014-07-21T11:18:00Z',
        'type_s': 'Project',
        '_version_': 1474236502200287232,
        'neighborhood_name_s': 'Projects',
        'id': 'allura/model/project/Project#53ccf6e8100d2b0741746e9f',
    }])

    def setup_method(self, method):
        super().setup_method(method)
        # Create project that matches TEST_HIT id
        _id = ObjectId('53ccf6e8100d2b0741746e9f')
        p = M.Project.query.get(_id=_id)
        if not p:
            M.Project(
                _id=_id,
                neighborhood_id=M.Neighborhood.query.get(url_prefix='/u/')._id,
                shortname='test-project',
            )
            ThreadLocalORMSession().flush_all()

    @patch('allura.controllers.site_admin.search')
    def test_default_fields(self, search):
        search.site_admin_search.return_value = self.TEST_HIT
        r = self.app.get('/nf/admin/search_projects?q=fake&f=shortname')
        options = [o['value'] for o in r.html.findAll('option')]
        assert options == ['shortname', 'name', '__custom__']
        ths = [th.text for th in r.html.findAll('th')]
        assert ths == ['Short name', 'Full name', 'Registered', 'Deleted?', 'Details']

    @patch('allura.controllers.site_admin.search')
    def test_additional_fields(self, search):
        search.site_admin_search.return_value = self.TEST_HIT
        with h.push_config(config, **{'search.project.additional_search_fields': 'private, url',
                                      'search.project.additional_display_fields': 'url'}):
            r = self.app.get('/nf/admin/search_projects?q=fake&f=shortname')
        options = [o['value'] for o in r.html.findAll('option')]
        assert options == ['shortname', 'name', 'private', 'url', '__custom__']
        ths = [th.text for th in r.html.findAll('th')]
        assert ths == ['Short name', 'Full name', 'Registered', 'Deleted?', 'url', 'Details']


class TestUsersSearch(TestController):

    TEST_HIT = MagicMock(hits=1, docs=[{
        '_version_': 1478773871277506560,
        'disabled_b': False,
        'pending_b': False,
        'display_name_t': 'Darth Vader',
        'id': 'allura/model/auth/User#540efdf2100d2b1483155d39',
        'last_access_login_date_dt': '2014-09-09T13:17:40.176Z',
        'last_access_login_ip_s': '10.0.2.2',
        'last_access_login_ua_t': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/37.0.2062.94 Safari/537.36',
        'last_access_session_date_dt': '2014-09-09T13:17:40.33Z',
        'last_access_session_ip_s': '10.0.2.2',
        'last_access_session_ua_t': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/37.0.2062.94 Safari/537.36',
        'last_password_updated_dt': '2014-09-09T13:17:38.857Z',
        'localization_s': 'None/None',
        'sex_s': 'Unknown',
        'title': ['User darth'],
        'type_s': 'User',
        'url_s': '/u/darth/',
        'user_registration_date_dt': '2014-09-09T13:17:38Z',
        'username_s': 'darth'}])

    def setup_method(self, method):
        super().setup_method(method)
        # Create user that matches TEST_HIT id
        _id = ObjectId('540efdf2100d2b1483155d39')
        u = M.User.query.get(_id=_id)
        if not u:
            M.User(_id=_id, username='darth')
            ThreadLocalORMSession().flush_all()

    @patch('allura.controllers.site_admin.search.site_admin_search')
    def test_default_fields(self, site_admin_search):
        site_admin_search.return_value = self.TEST_HIT
        r = self.app.get('/nf/admin/search_users?q=fake&f=username')
        options = [o['value'] for o in r.html.findAll('option')]
        assert options == ['username', 'display_name', '__custom__']
        ths = [th.text for th in r.html.findAll('th')]
        assert ths == ['Username', 'Display name', 'Email', 'Registered',
                           'Status', 'Details']

    @patch('allura.controllers.site_admin.search.site_admin_search')
    def test_additional_fields(self, site_admin_search):
        site_admin_search.return_value = self.TEST_HIT
        with h.push_config(config, **{'search.user.additional_search_fields': 'email_addresses, url',
                                      'search.user.additional_display_fields': 'url'}):
            r = self.app.get('/nf/admin/search_users?q=fake&f=username')
        options = [o['value'] for o in r.html.findAll('option')]
        assert options == ['username', 'display_name', 'email_addresses', 'url', '__custom__']
        ths = [th.text for th in r.html.findAll('th')]
        assert ths == ['Username', 'Display name', 'Email', 'Registered',
                           'Status', 'url', 'Details']


class TestUserDetails(TestController):

    def test_404(self):
        self.app.get('/nf/admin/user/does-not-exist', status=404)

    def test_general_info(self):
        user = M.User.by_username('test-admin')
        user.registration_date = lambda: dt.datetime(2014, 9, 1, 9, 9, 9)
        user.last_access = {'login_date': dt.datetime(2014, 9, 2, 6, 6, 6),
                            'login_ua': 'browser of the future 1.0',
                            'login_ip': '8.8.8.8',
                            'session_date': dt.datetime(2014, 9, 12, 6, 6, 6),
                            'session_ua': 'browser of the future 1.1',
                            'session_ip': '7.7.7.7'}
        r = self.app.get('/nf/admin/user/test-admin')
        # general info
        assert 'Username: test-admin' in r
        assert 'Full name: Test Admin' in r
        assert 'Registered: 2014-09-01 09:09:09' in r
        # session info
        assert 'Date: 2014-09-02 06:06:06' in r
        assert 'IP: 8.8.8.8' in r
        assert 'UA: browser of the future 1.0' in r
        assert 'Date: 2014-09-12' in r
        assert 'IP: 7.7.7.7' in r
        assert 'UA: browser of the future 1.1' in r
        # list of projects
        projects = r.html.findAll('fieldset')[-1]
        projects = [e.getText() for e in projects.findAll('li')]
        assert 'Test 2\n\u2013\nAdmin\n' in projects
        assert 'Test Project\n\u2013\nAdmin\n' in projects
        assert 'Adobe project 1\n\u2013\nAdmin\n' in projects

    @patch('allura.model.auth.request')
    @patch('allura.lib.helpers.request')
    def test_audit_log(self, req1, req2):
        req1.url = req2.url = 'http://host.domain/path/'
        c.user = M.User.by_username('test-user-1')
        h.auditlog_user('test activity user 1')
        h.auditlog_user('test activity user 2', user=M.User.by_username('test-user-2'))
        r = self.app.get('/nf/admin/user/test-admin')
        assert 'Add comment' in r
        assert 'test activity' not in r
        r = self.app.get('/nf/admin/user/test-user-1')
        assert 'test activity user 1' in r
        assert 'test activity user 2' not in r
        r = self.app.get('/nf/admin/user/test-user-2')
        assert 'test activity user 1' not in r
        assert 'test activity user 2' in r

    def test_add_audit_trail_entry_access(self):
        self.app.get('/nf/admin/user/add_audit_log_entry', status=404)  # GET is not allowed
        r = self.app.post('/nf/admin/user/add_audit_log_entry',
                          extra_environ={'username': '*anonymous'},
                          status=302)
        assert r.location == 'http://localhost/auth/'

    def test_add_comment(self):
        r = self.app.get('/nf/admin/user/test-user')
        assert 'Comment by test-admin: I was hêre!' not in r
        form = [f for f in r.forms.values() if f.action.endswith('add_audit_trail_entry')][0]
        assert form['username'].value == 'test-user'
        form['comment'] = 'I was hêre!'
        r = form.submit()
        assert 'Comment added' in self.webflash(r)
        r = self.app.get('/nf/admin/user/test-user')
        assert 'Comment by test-admin: I was hêre!' in r

    def test_disable_user(self):
        # user was not pending
        assert M.User.by_username('test-user-3').disabled is False
        assert M.User.by_username('test-user-3').pending is False
        r = self.app.get('/nf/admin/user/test-user-3')
        form = r.forms[0]
        assert form['username'].value == 'test-user-3'
        assert form['status'].value == 'enable'
        form['status'].value = 'disable'
        with td.audits('Account disabled', user=True):
            r = form.submit()
            assert M.AuditLog.query.find().count() == 1
        assert 'User disabled' in self.webflash(r)
        assert M.User.by_username('test-user-3').disabled is True
        assert M.User.by_username('test-user-3').pending is False

        # user was pending
        user = M.User.by_username('test-user-3')
        user.disabled = False
        user.pending = True
        ThreadLocalORMSession.flush_all()
        assert M.User.by_username('test-user-3').disabled is False
        assert M.User.by_username('test-user-3').pending is True
        r = self.app.get('/nf/admin/user/test-user-3')
        form = r.forms[0]
        assert form['username'].value == 'test-user-3'
        assert form['status'].value == 'pending'
        form['status'].value = 'disable'
        with td.audits('Account disabled', user=True):
            r = form.submit()
            assert M.AuditLog.query.find().count() == 1
        assert 'User disabled' in self.webflash(r)
        assert M.User.by_username('test-user-3').disabled is True
        assert M.User.by_username('test-user-3').pending is True

    def test_enable_user(self):
        # user was not pending
        user = M.User.by_username('test-user-3')
        user.disabled = True
        ThreadLocalORMSession.flush_all()
        assert M.User.by_username('test-user-3').disabled is True
        assert M.User.by_username('test-user-3').pending is False
        r = self.app.get('/nf/admin/user/test-user-3')
        form = r.forms[0]
        assert form['username'].value == 'test-user-3'
        assert form['status'].value == 'disable'
        form['status'].value = 'enable'
        with td.audits('Account enabled', user=True):
            r = form.submit()
            assert M.AuditLog.query.find().count() == 1
        assert 'User enabled' in self.webflash(r)
        assert M.User.by_username('test-user-3').disabled is False
        assert M.User.by_username('test-user-3').pending is False

        # user was pending
        user = M.User.by_username('test-user-3')
        user.disabled = False
        user.pending = True
        ThreadLocalORMSession.flush_all()
        assert M.User.by_username('test-user-3').disabled is False
        assert M.User.by_username('test-user-3').pending is True
        r = self.app.get('/nf/admin/user/test-user-3')
        form = r.forms[0]
        assert form['username'].value == 'test-user-3'
        assert form['status'].value == 'pending'
        form['status'].value = 'enable'
        with td.audits('Account activated', user=True):
            r = form.submit()
            assert M.AuditLog.query.find().count() == 1
        assert 'User enabled' in self.webflash(r)
        assert M.User.by_username('test-user-3').disabled is False
        assert M.User.by_username('test-user-3').pending is False

        # user was pending and disabled
        user = M.User.by_username('test-user-3')
        user.disabled = True
        user.pending = True
        ThreadLocalORMSession.flush_all()
        assert M.User.by_username('test-user-3').disabled is True
        assert M.User.by_username('test-user-3').pending is True
        r = self.app.get('/nf/admin/user/test-user-3')
        form = r.forms[0]
        assert form['username'].value == 'test-user-3'
        assert form['status'].value == 'disable'
        form['status'].value = 'enable'
        with td.audits('Account enabled', user=True):
            r = form.submit()
            assert M.AuditLog.query.find().count() == 1
        assert 'User enabled' in self.webflash(r)
        assert M.User.by_username('test-user-3').disabled is False
        assert M.User.by_username('test-user-3').pending is False

    def test_set_pending(self):
        # user was disabled
        user = M.User.by_username('test-user-3')
        user.disabled = True
        ThreadLocalORMSession.flush_all()
        assert M.User.by_username('test-user-3').disabled is True
        assert M.User.by_username('test-user-3').pending is False
        r = self.app.get('/nf/admin/user/test-user-3')
        form = r.forms[0]
        assert form['username'].value == 'test-user-3'
        assert form['status'].value == 'disable'
        form['status'].value = 'pending'
        with td.audits('Account changed to pending', user=True):
            r = form.submit()
            assert M.AuditLog.query.find().count() == 1
        assert 'Set user status to pending' in self.webflash(r)
        assert M.User.by_username('test-user-3').disabled is False
        assert M.User.by_username('test-user-3').pending is True

        # user was enabled
        user = M.User.by_username('test-user-3')
        user.pending = False
        user.disabled = False
        ThreadLocalORMSession.flush_all()
        assert M.User.by_username('test-user-3').disabled is False
        assert M.User.by_username('test-user-3').pending is False
        r = self.app.get('/nf/admin/user/test-user-3')
        form = r.forms[0]
        assert form['username'].value == 'test-user-3'
        assert form['status'].value == 'enable'
        form['status'].value = 'pending'
        with td.audits('Account changed to pending', user=True):
            r = form.submit()
            assert M.AuditLog.query.find().count() == 1
        assert 'Set user status to pending' in self.webflash(r)
        assert M.User.by_username('test-user-3').disabled is False
        assert M.User.by_username('test-user-3').pending is True

    def test_emails(self):
        # add test@example.com
        with td.audits('New email address: test@example.com', user=True):
            r = self.app.post('/nf/admin/user/update_emails', params={
                'username': 'test-user',
                'new_addr.addr': 'test@example.com',
                'new_addr.claim': 'Claim Address',
                'primary_addr': 'test@example.com'},
                extra_environ=dict(username='test-admin'))
        r = self.app.get('/nf/admin/user/test-user')
        assert 'test@example.com' in r
        em = M.EmailAddress.get(email='test@example.com')
        assert em.confirmed is True
        user = M.User.query.get(username='test-user')
        assert user.get_pref('email_address') == 'test@example.com'

        # add test2@example.com
        with td.audits('New email address: test2@example.com', user=True):
            r = self.app.post('/nf/admin/user/update_emails', params={
                'username': 'test-user',
                'new_addr.addr': 'test2@example.com',
                'new_addr.claim': 'Claim Address',
                'primary_addr': 'test@example.com'},
                extra_environ=dict(username='test-admin'))
        r = self.app.get('/nf/admin/user/test-user')
        assert 'test2@example.com' in r
        em = M.EmailAddress.get(email='test2@example.com')
        assert em.confirmed is True
        user = M.User.query.get(username='test-user')
        assert user.get_pref('email_address') == 'test@example.com'

        # change primary: test -> test2
        with td.audits('Primary email changed: test@example.com => test2@example.com', user=True):
            r = self.app.post('/nf/admin/user/update_emails', params={
                'username': 'test-user',
                'new_addr.addr': '',
                'primary_addr': 'test2@example.com'},
                extra_environ=dict(username='test-admin'))
        r = self.app.get('/nf/admin/user/test-user')
        user = M.User.query.get(username='test-user')
        assert user.get_pref('email_address') == 'test2@example.com'

        # remove test2@example.com
        with td.audits('Email address deleted: test2@example.com', user=True):
            r = self.app.post('/nf/admin/user/update_emails', params={
                'username': 'test-user',
                'addr-1.ord': '1',
                'addr-2.ord': '2',
                'addr-3.ord': '3',
                'addr-3.delete': 'on',
                'new_addr.addr': '',
                'primary_addr': 'test2@example.com'},
                extra_environ=dict(username='test-admin'))
        r = self.app.get('/nf/admin/user/test-user')
        user = M.User.query.get(username='test-user')
        # test@example.com set as primary since test2@example.com is deleted
        assert user.get_pref('email_address') == 'test-user@allura.local'

    @patch.object(LocalAuthenticationProvider, 'set_password')
    def test_set_random_password(self, set_password):
        with td.audits('Set random password', user=True, actor='test-admin'):
            r = self.app.post('/nf/admin/user/set_random_password', params={'username': 'test-user'})
        assert 'Password is set' in self.webflash(r)
        assert set_password.call_count == 1

    @patch('allura.tasks.mail_tasks.sendsimplemail')
    @patch('allura.lib.helpers.gen_message_id')
    def test_send_password_reset_link(self, gen_message_id, sendmail):
        user = M.User.by_username('test-user')
        user.set_pref('email_address', 'test-user@example.org')
        M.EmailAddress(email='test-user@example.org', confirmed=True, claimed_by_user_id=user._id)
        ThreadLocalORMSession.flush_all()
        with td.audits('Password recovery link sent to: test-user@example.org', user=True):
            r = self.app.post('/nf/admin/user/send_password_reset_link', params={'username': 'test-user'})
        hash = user.get_tool_data('AuthPasswordReset', 'hash')
        text = '''Your username is test-user

To update your password on %s, please visit the following URL:

%s/auth/forgotten_password/%s''' % (config['site_name'], config['base_url'], hash)
        sendmail.post.assert_called_once_with(
            sender='noreply@localhost',
            toaddr='test-user@example.org',
            fromaddr='"{}" <{}>'.format(config['site_name'], config['forgemail.return_path']),
            reply_to=config['forgemail.return_path'],
            subject='Allura Password recovery',
            message_id=gen_message_id(),
            text=text)

    def test_make_password_reset_url(self):
        with td.audits('Generated new password reset URL and shown to admin user', user=True):
            r = self.app.post('/nf/admin/user/make_password_reset_url', params={'username': 'test-user'})
        user = M.User.by_username('test-user')
        hash = user.get_tool_data('AuthPasswordReset', 'hash')
        assert hash in r.text


class TestDeleteProjects(TestController):

    def confirm_form(self, r):
        return self.find_form(r, lambda f: f.action == 'really_delete')

    def delete_form(self, r):
        return self.find_form(r, lambda f: f.action == 'confirm')

    def test_projects_populated_from_get_params(self):
        r = self.app.get('/nf/admin/delete_projects/')
        assert self.delete_form(r)['projects'].value == ''
        link = '/nf/admin/delete_projects/?projects=/p/test/++++%23+comment%0A/adobe/adobe-1/%0A/p/test2/'
        link += '&reason=The%0AReason&disable_users=True'
        r = self.app.get(link)
        form = self.delete_form(r)
        assert form['projects'].value == '/p/test/    # comment\n/adobe/adobe-1/\n/p/test2/'
        assert form['reason'].value == 'The\nReason'
        assert form['disable_users'].value == 'on'

    def test_confirm_step_values(self):
        r = self.app.get('/nf/admin/delete_projects/')
        form = self.delete_form(r)
        form['projects'] = 'p/test\ndne/dne'
        form['reason'] = 'The Reason'
        form['disable_users'] = True
        r = form.submit()
        confirm_form = self.confirm_form(r)
        for f in ['reason', 'disable_users']:
            assert confirm_form[f].value == form[f].value
        assert confirm_form['projects'].value == 'p/test    # OK: /p/test/\ndne/dne    # Neighborhood not found'

        confirm_data = r.html.find('table').findAll('td')
        assert len(confirm_data) == 4  # 2 projects == 2 rows (2 columns each)
        assert confirm_data[0].getText() == 'p/test'
        assert confirm_data[1].find('a').get('href') == '/p/test/'
        assert confirm_data[1].getText().strip() == '/p/test/'
        assert confirm_data[2].getText().strip() == 'dne/dne'
        assert confirm_data[3].getText().strip() == 'Neighborhood not found'

    def test_confirm_step_edit_link(self):
        r = self.app.get('/nf/admin/delete_projects/')
        form = self.delete_form(r)
        form['projects'] = 'p/test\np/dne'
        form['reason'] = 'The Reason\nMultiline'
        form['disable_users'] = True
        r = form.submit()
        expected_href = './?projects=p/test++++%23+OK:+/p/test%0Ap/dne++++%23+Project not found'
        expected_href += '&reason=The+Reason%0AMultiline&disable_users=True'
        assert r.html.findAll('a', {'href': expected_href}) is not None

    @patch('allura.controllers.site_admin.DeleteProjects', autospec=True)
    def test_reason_passed_to_task(self, dp):
        data = {'projects': 'p/test2', 'reason': 'Because "I can and want"'}
        self.app.post('/nf/admin/delete_projects/really_delete', data)
        dp.post.assert_called_once_with('-r \'Because "I can and want"\' p/test2')

    @patch('allura.controllers.site_admin.DeleteProjects', autospec=True)
    def test_multiline_reason_passed_to_task(self, dp):
        data = {'projects': 'p/test2', 'reason': 'Because\nI want'}
        self.app.post('/nf/admin/delete_projects/really_delete', data)
        dp.post.assert_called_once_with('-r \'Because\nI want\' p/test2')

    @patch('allura.controllers.site_admin.DeleteProjects', autospec=True)
    def test_task_fires(self, dp):
        data = {'projects': '/p/test\nhttp://localhost:8080/adobe/adobe-1\np/test2'}
        self.app.post('/nf/admin/delete_projects/really_delete', data)
        dp.post.assert_called_once_with('p/test adobe/adobe-1 p/test2')

    @patch('allura.controllers.site_admin.DeleteProjects', autospec=True)
    def test_comments_are_ignored(self, dp):
        data = {'projects': '''/p/test    # comment
                               /p/test2   # comment 2'''}
        self.app.post('/nf/admin/delete_projects/really_delete', data)
        dp.post.assert_called_once_with('p/test p/test2')

    @patch('allura.controllers.site_admin.DeleteProjects', autospec=True)
    def test_admins_and_devs_are_disabled(self, dp):
        data = {'projects': '/p/test\np/test2', 'disable_users': 'True'}
        self.app.post('/nf/admin/delete_projects/really_delete', data)
        dp.post.assert_called_once_with('--disable-users p/test p/test2')

    @patch('allura.controllers.site_admin.DeleteProjects', autospec=True)
    def test_subproject_delete(self, dp):
        data = {'projects': '/p/test/sub1/something\np/test2'}
        self.app.post('/nf/admin/delete_projects/really_delete', data)
        dp.post.assert_called_once_with('p/test/sub1 p/test2')

    @td.with_user_project('test-user')
    @patch('allura.controllers.site_admin.DeleteProjects', autospec=True)
    def test_userproject_delete(self, dp):
        data = {'projects': '/u/test-user'}
        self.app.post('/nf/admin/delete_projects/really_delete', data)
        dp.post.assert_called_once_with('u/test-user')


@task
def test_task(*args, **kw):
    """test_task doc string"""
    pass
