# coding: utf-8
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

from mock import patch, MagicMock
from nose.tools import assert_equal, assert_in, assert_not_in
from ming.odm import ThreadLocalORMSession
from pylons import tmpl_context as c
from tg import config
from bson import ObjectId

from allura import model as M
from allura.tests import TestController
from allura.lib import helpers as h
from allura.lib.decorators import task


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
            'h2', {'class': 'dark title'}).contents[0]
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
        assert_equal(len(r.html.find('table').findAll('tr')), count - 1)

    def test_new_projects_daterange_filtering(self):
        r = self.app.get('/nf/admin/new_projects', extra_environ=dict(
            username='root'))
        count = len(r.html.find('table').findAll('tr'))
        assert_equal(count, 7)

        filtr = r.forms[0]
        filtr['start-dt'] = '2000/01/01 10:10:10'
        filtr['end-dt'] = '2000/01/01 09:09:09'
        r = filtr.submit()
        count = len(r.html.find('table').findAll('tr'))
        assert_equal(count, 1)  # only row with headers - no results

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
        import math
        task = M.MonQTask.post(math.ceil, (12.5,))
        url = '/nf/admin/task_manager/view/%s' % task._id
        r = self.app.get(
            url, extra_environ=dict(username='*anonymous'), status=302)
        r = self.app.get(url)
        assert 'math.ceil' in r, r

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
        task = M.MonQTask.query.find({}).sort('_id', -1).next()
        assert str(task._id) in r.location
        assert task.context['project_id'] == project._id
        assert task.context['app_config_id'] == app.config._id
        assert task.context['user_id'] == user._id
        assert task.args == task_args['args']
        assert task.kwargs == task_args['kwargs']

    def test_task_doc(self):
        r = self.app.get('/nf/admin/task_manager/task_doc', params=dict(
            task_name='allura.tests.functional.test_site_admin.test_task'))
        assert json.loads(r.body)['doc'] == 'test_task doc string'

    @patch('allura.model.auth.request')
    @patch('allura.lib.helpers.request')
    def test_users(self, req1, req2):
        req1.url = req2.url = 'http://host.domain/path/'
        c.user = M.User.by_username('test-user-1')
        h.auditlog_user('test activity user 1')
        h.auditlog_user('test activity user 2', user=M.User.by_username('test-user-2'))
        r = self.app.get('/nf/admin/users')
        assert_not_in('test activity', r)
        r = self.app.get('/nf/admin/users?username=admin1')
        assert_not_in('test activity', r)
        r = self.app.get('/nf/admin/users?username=test-user-1')
        assert_in('test activity user 1', r)
        assert_not_in('test activity user 2', r)
        r = self.app.get('/nf/admin/users?username=test-user-2')
        assert_not_in('test activity user 1', r)
        assert_in('test activity user 2', r)

    def test_add_audit_trail_entry_access(self):
        self.app.get('/nf/admin/add_audit_log_entry', status=404)  # GET is not allowed
        r = self.app.post('/nf/admin/add_audit_log_entry',
                          extra_environ={'username': '*anonymous'},
                          status=302)
        assert_equal(r.location, 'http://localhost/auth/')

    def test_add_comment_on_users_trail_page(self):
        r = self.app.get('/nf/admin/users')
        assert_not_in('Add comment', r)
        r = self.app.get('/nf/admin/users?username=fake-user')
        assert_not_in('Add comment', r)
        r = self.app.get('/nf/admin/users?username=test-user')
        assert_in('Add comment', r)

    def test_add_comment(self):
        r = self.app.get('/nf/admin/users?username=test-user')
        assert_not_in(u'Comment by test-admin: I was hêre!', r)
        form = r.forms[1]
        assert_equal(form['username'].value, 'test-user')
        form['comment'] = u'I was hêre!'
        r = form.submit()
        assert_in(u'Comment added', self.webflash(r))
        r = self.app.get('/nf/admin/users?username=test-user')
        assert_in(u'Comment by test-admin: I was hêre!', r)


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

    def setUp(self):
        super(TestProjectsSearch, self).setUp()
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
        assert_equal(options, ['shortname', 'name', '__custom__'])
        ths = [th.text for th in r.html.findAll('th')]
        assert_equal(ths, ['Short name', 'Full name', 'Registered', 'Deleted?', 'Details'])

    @patch('allura.controllers.site_admin.search')
    def test_additional_fields(self, search):
        search.site_admin_search.return_value = self.TEST_HIT
        with h.push_config(config, **{'search.project.additional_search_fields': 'private, url',
                                      'search.project.additional_display_fields': 'url'}):
            r = self.app.get('/nf/admin/search_projects?q=fake&f=shortname')
        options = [o['value'] for o in r.html.findAll('option')]
        assert_equal(options, ['shortname', 'name', 'private', 'url', '__custom__'])
        ths = [th.text for th in r.html.findAll('th')]
        assert_equal(ths, ['Short name', 'Full name', 'Registered', 'Deleted?', 'url', 'Details'])


class TestUsersSearch(TestController):

    TEST_HIT = MagicMock(hits=1, docs=[{
        '_version_': 1478773871277506560,
        'disabled_b': False,
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

    def setUp(self):
        super(TestUsersSearch, self).setUp()
        # Create user that matches TEST_HIT id
        _id = ObjectId('540efdf2100d2b1483155d39')
        u = M.User.query.get(_id=_id)
        if not u:
            M.User(_id=_id, username='darth')
            ThreadLocalORMSession().flush_all()

    @patch('allura.controllers.site_admin.search')
    def test_default_fields(self, search):
        search.site_admin_search.return_value = self.TEST_HIT
        r = self.app.get('/nf/admin/search_users?q=fake&f=username')
        options = [o['value'] for o in r.html.findAll('option')]
        assert_equal(options, ['username', 'display_name', '__custom__'])
        ths = [th.text for th in r.html.findAll('th')]
        assert_equal(ths, ['Username', 'Display name', 'Email', 'Registered',
                           'Disabled?', 'Details'])

    @patch('allura.controllers.site_admin.search')
    def test_additional_fields(self, search):
        search.site_admin_search.return_value = self.TEST_HIT
        with h.push_config(config, **{'search.user.additional_search_fields': 'email_addresses, url',
                                      'search.user.additional_display_fields': 'url'}):
            r = self.app.get('/nf/admin/search_users?q=fake&f=username')
        options = [o['value'] for o in r.html.findAll('option')]
        assert_equal(options, ['username', 'display_name', 'email_addresses', 'url', '__custom__'])
        ths = [th.text for th in r.html.findAll('th')]
        assert_equal(ths, ['Username', 'Display name', 'Email', 'Registered',
                           'Disabled?', 'url', 'Details'])


class TestUserDetails(TestController):

    def test_404(self):
        self.app.get('/nf/admin/user/does-not-exist/', status=404)

    def test_general_info(self):
        user = M.User.by_username('test-admin')
        user.registration_date = lambda: dt.datetime(2014, 9, 1, 9, 9, 9)
        user.last_access = {'login_date': dt.datetime(2014, 9, 2, 6, 6, 6),
                            'login_ua': 'browser of the future 1.0',
                            'login_ip': '8.8.8.8',
                            'session_date': dt.datetime(2014, 9, 12, 6, 6, 6),
                            'session_ua': 'browser of the future 1.1',
                            'session_ip': '7.7.7.7'}
        r = self.app.get('/nf/admin/user/test-admin/')
        # general info
        assert_in('Username: test-admin', r)
        assert_in('Full name: Test Admin', r)
        assert_in('Registered: 2014-09-01 09:09:09', r)
        # session info
        assert_in('Date: 2014-09-02 06:06:06', r)
        assert_in('IP: 8.8.8.8', r)
        assert_in('UA: browser of the future 1.0', r)
        assert_in('Date: 2014-09-12 06:06:06', r)
        assert_in('IP: 7.7.7.7', r)
        assert_in('UA: browser of the future 1.1', r)
        # list of projects
        projects = r.html.findAll('fieldset')[-1]
        projects = [e.getText() for e in projects.findAll('li')]
        assert_in('Test 2', projects)
        assert_in('Test Project', projects)
        assert_in('Adobe project 1', projects)

    @patch('allura.model.auth.request')
    @patch('allura.lib.helpers.request')
    def test_audit_log(self, req1, req2):
        req1.url = req2.url = 'http://host.domain/path/'
        c.user = M.User.by_username('test-user-1')
        h.auditlog_user('test activity user 1')
        h.auditlog_user('test activity user 2', user=M.User.by_username('test-user-2'))
        r = self.app.get('/nf/admin/user/test-admin')
        assert_in('Add comment', r)
        assert_not_in('test activity', r)
        r = self.app.get('/nf/admin/user/test-user-1')
        assert_in('test activity user 1', r)
        assert_not_in('test activity user 2', r)
        r = self.app.get('/nf/admin/user/test-user-2')
        assert_not_in('test activity user 1', r)
        assert_in('test activity user 2', r)

    def test_add_audit_trail_entry_access(self):
        self.app.get('/nf/admin/user/add_audit_log_entry', status=404)  # GET is not allowed
        r = self.app.post('/nf/admin/user/add_audit_log_entry',
                          extra_environ={'username': '*anonymous'},
                          status=302)
        assert_equal(r.location, 'http://localhost/auth/')

    def test_add_comment(self):
        r = self.app.get('/nf/admin/user/test-user')
        assert_not_in(u'Comment by test-admin: I was hêre!', r)
        form = r.forms[2]
        assert_equal(form['username'].value, 'test-user')
        form['comment'] = u'I was hêre!'
        r = form.submit()
        assert_in(u'Comment added', self.webflash(r))
        r = self.app.get('/nf/admin/user/test-user')
        assert_in(u'Comment by test-admin: I was hêre!', r)

    def test_disable_user(self):
        assert_equal(M.User.by_username('test-user').disabled, False)
        r = self.app.get('/nf/admin/user/test-user')
        form = r.forms[0]
        assert_equal(form['username'].value, 'test-user')
        assert_equal(form['status'].value, 'enable')
        form['status'].value = 'disable'
        r = form.submit()
        assert_in(u'User disabled', self.webflash(r))
        assert_equal(M.User.by_username('test-user').disabled, True)

    def test_enable_user(self):
        user = M.User.by_username('test-user')
        user.disabled = True
        ThreadLocalORMSession.flush_all()
        assert_equal(M.User.by_username('test-user').disabled, True)
        r = self.app.get('/nf/admin/user/test-user')
        form = r.forms[0]
        assert_equal(form['username'].value, 'test-user')
        assert_equal(form['status'].value, 'disable')
        form['status'].value = 'enable'
        r = form.submit()
        assert_in(u'User enabled', self.webflash(r))
        assert_equal(M.User.by_username('test-user').disabled, False)

@task
def test_task(*args, **kw):
    """test_task doc string"""
    pass
