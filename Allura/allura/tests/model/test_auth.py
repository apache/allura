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
Model tests for auth
"""

import textwrap
from datetime import datetime, timedelta

from tg import tmpl_context as c, app_globals as g, request as r
from webob import Request
from mock import patch, Mock

from ming.orm.ormsession import ThreadLocalORMSession
from ming.odm import session

from allura import model as M
from allura.lib import helpers as h
from allura.lib import plugin
from allura.tests import decorators as td
from alluratest.controller import setup_basic_test, setup_global_objects, setup_functional_test, setup_unit_test


class TestAuth:

    def setup_method(self):
        setup_basic_test()
        setup_global_objects()

    def test_email_address(self):
        addr = M.EmailAddress(email='test_admin@domain.net',
                              claimed_by_user_id=c.user._id)
        ThreadLocalORMSession.flush_all()
        assert addr.claimed_by_user() == c.user
        addr2 = M.EmailAddress.create('test@domain.net')
        addr3 = M.EmailAddress.create('test_admin@domain.net')
        ThreadLocalORMSession.flush_all()

        # Duplicate emails are allowed, until the email is confirmed
        assert addr3 is not addr

        assert addr2 is not addr
        assert addr2
        addr4 = M.EmailAddress.create('test@DOMAIN.NET')
        assert addr4 is not addr2

        assert addr is c.user.address_object('test_admin@domain.net')
        c.user.claim_address('test@DOMAIN.NET')
        assert 'test@domain.net' in c.user.email_addresses

    def selftest_email_address_lookup_helpers():
        addr = M.EmailAddress.create('TEST@DOMAIN.NET')
        nobody = M.EmailAddress.create('nobody@example.com')
        ThreadLocalORMSession.flush_all()
        assert addr.email == 'TEST@domain.net'

        assert M.EmailAddress.get(email='TEST@DOMAIN.NET') == addr
        assert M.EmailAddress.get(email='TEST@domain.net') == addr
        assert M.EmailAddress.get(email='test@domain.net') is None
        assert M.EmailAddress.get(email=None) is None
        assert M.EmailAddress.get(email='nobody@example.com') == nobody
        # invalid email returns None, but not nobody@example.com as before
        assert M.EmailAddress.get(email='invalid') is None

        assert M.EmailAddress.find(dict(email='TEST@DOMAIN.NET')).all() == [addr]
        assert M.EmailAddress.find(dict(email='TEST@domain.net')).all() == [addr]
        assert M.EmailAddress.find(dict(email='test@domain.net')).all() == []
        assert M.EmailAddress.find(dict(email=None)).all() == []
        assert M.EmailAddress.find(dict(email='nobody@example.com')).all() == [nobody]
        # invalid email returns empty query, but not nobody@example.com as before
        assert M.EmailAddress.find(dict(email='invalid')).all() == []

    def test_email_address_canonical(self):
        assert M.EmailAddress.canonical('nobody@EXAMPLE.COM') == \
               'nobody@example.com'
        assert M.EmailAddress.canonical('nobody@example.com') == \
               'nobody@example.com'
        assert M.EmailAddress.canonical('I Am Nobody <nobody@example.com>') == \
               'nobody@example.com'
        assert M.EmailAddress.canonical('  nobody@example.com\t') == \
               'nobody@example.com'
        assert M.EmailAddress.canonical('I Am@Nobody <nobody@example.com> ') == \
               'nobody@example.com'
        assert M.EmailAddress.canonical(' No@body <no@body@example.com> ') == \
               'no@body@example.com'
        assert M.EmailAddress.canonical('no@body@example.com') == \
               'no@body@example.com'
        assert M.EmailAddress.canonical('invalid') is None

    def test_email_address_send_verification_link(self):
        addr = M.EmailAddress(email='test_admin@domain.net',
                              claimed_by_user_id=c.user._id)

        addr.send_verification_link()

        with patch('allura.tasks.mail_tasks.smtp_client._client') as _client:
            M.MonQTask.run_ready()
        return_path, rcpts, body = _client.sendmail.call_args[0]
        assert rcpts == ['test_admin@domain.net']

    @td.with_user_project('test-admin')
    def test_user(self):
        assert c.user.url() .endswith('/u/test-admin/')
        assert c.user.script_name .endswith('/u/test-admin/')
        assert ({p.shortname for p in c.user.my_projects()} ==
                {'test', 'test2', 'u/test-admin', 'adobe-1', '--init--'})
        # delete one of the projects and make sure it won't appear in my_projects()
        p = M.Project.query.get(shortname='test2')
        p.deleted = True
        ThreadLocalORMSession.flush_all()
        assert ({p.shortname for p in c.user.my_projects()} ==
                {'test', 'u/test-admin', 'adobe-1', '--init--'})
        u = M.User.register(dict(
            username='nosetest-user'))
        ThreadLocalORMSession.flush_all()
        assert u.reg_date
        assert u.private_project().shortname == 'u/nosetest-user'
        roles = g.credentials.user_roles(
            u._id, project_id=u.private_project().root_project._id)
        assert len(roles) == 3, roles
        u.set_password('foo')
        provider = plugin.LocalAuthenticationProvider(Request.blank('/'))
        assert provider._validate_password(u, 'foo')
        assert not provider._validate_password(u, 'foobar')
        u.set_password('foobar')
        assert provider._validate_password(u, 'foobar')
        assert not provider._validate_password(u, 'foo')

    def test_user_project_creates_on_demand(self):
        u = M.User.register(dict(username='foobar123'), make_project=False)
        ThreadLocalORMSession.flush_all()
        assert not M.Project.query.get(shortname='u/foobar123')
        assert u.private_project()
        assert M.Project.query.get(shortname='u/foobar123')

    def test_user_project_already_deleted_creates_on_demand(self):
        u = M.User.register(dict(username='foobar123'), make_project=True)
        p = M.Project.query.get(shortname='u/foobar123')
        p.deleted = True
        ThreadLocalORMSession.flush_all()
        assert not M.Project.query.get(shortname='u/foobar123', deleted=False)
        assert u.private_project()
        ThreadLocalORMSession.flush_all()
        assert M.Project.query.get(shortname='u/foobar123', deleted=False)

    def test_user_project_does_not_create_on_demand_for_disabled_user(self):
        u = M.User.register(
            dict(username='foobar123', disabled=True), make_project=False)
        ThreadLocalORMSession.flush_all()
        assert not u.private_project()
        assert not M.Project.query.get(shortname='u/foobar123')

    def test_user_project_does_not_create_on_demand_for_anonymous_user(self):
        u = M.User.anonymous()
        ThreadLocalORMSession.flush_all()
        assert not u.private_project()
        assert not M.Project.query.get(shortname='u/anonymous')
        assert not M.Project.query.get(shortname='u/*anonymous')

    @patch('allura.model.auth.log')
    def test_user_by_email_address(self, log):
        u1 = M.User.register(dict(username='abc1'), make_project=False)
        u2 = M.User.register(dict(username='abc2'), make_project=False)
        addr1 = M.EmailAddress(email='abc123@abc.me', confirmed=True,
                               claimed_by_user_id=u1._id)
        addr2 = M.EmailAddress(email='abc123@abc.me', confirmed=True,
                               claimed_by_user_id=u2._id)
        # both users are disabled
        u1.disabled, u2.disabled = True, True
        ThreadLocalORMSession.flush_all()
        assert M.User.by_email_address('abc123@abc.me') is None
        assert log.warn.call_count == 0

        # only u2 is active
        u1.disabled, u2.disabled = True, False
        ThreadLocalORMSession.flush_all()
        assert M.User.by_email_address('abc123@abc.me') == u2
        assert log.warn.call_count == 0

        # both are active
        u1.disabled, u2.disabled = False, False
        ThreadLocalORMSession.flush_all()
        assert M.User.by_email_address('abc123@abc.me') in [u1, u2]
        assert log.warn.call_count == 1

        # invalid email returns None, but not user which claimed
        # nobody@example.com as before
        nobody = M.EmailAddress(email='nobody@example.com', confirmed=True,
                                claimed_by_user_id=u1._id)
        ThreadLocalORMSession.flush_all()
        assert M.User.by_email_address('nobody@example.com') == u1
        assert M.User.by_email_address('invalid') is None

    def test_user_equality(self):
        assert M.User.by_username('test-user') == M.User.by_username('test-user')
        assert M.User.anonymous() == M.User.anonymous()
        assert M.User.by_username('*anonymous') == M.User.anonymous()

        assert M.User.by_username('test-user') != M.User.by_username('test-admin')
        assert M.User.by_username('test-user') != M.User.anonymous()
        assert M.User.anonymous() is not None
        assert M.User.anonymous() != 12345
        assert M.User.anonymous() != M.User()

    def test_user_hash(self):
        assert M.User.by_username('test-user') in {M.User.by_username('test-user')}
        assert M.User.anonymous() in {M.User.anonymous()}
        assert M.User.by_username('*anonymous') in {M.User.anonymous()}

        assert M.User.by_username('test-user') not in {M.User.by_username('test-admin')}
        assert M.User.anonymous() not in {M.User.by_username('test-admin')}
        assert M.User.anonymous() not in {0, None}

    def test_project_role(self):
        role = M.ProjectRole(project_id=c.project._id, name='test_role')
        M.ProjectRole.by_user(c.user, upsert=True).roles.append(role._id)
        ThreadLocalORMSession.flush_all()
        roles = g.credentials.user_roles(
            c.user._id, project_id=c.project.root_project._id)
        roles_ids = [r['_id'] for r in roles]
        roles = M.ProjectRole.query.find({'_id': {'$in': roles_ids}})
        for pr in roles:
            assert pr.display()
            pr.special
            assert pr.user in (c.user, None, M.User.anonymous())

    def test_default_project_roles(self):
        roles = {
            pr.name: pr
            for pr in M.ProjectRole.query.find(dict(
                project_id=c.project._id)).all()
            if pr.name}
        assert 'Admin' in list(roles.keys()), list(roles.keys())
        assert 'Developer' in list(roles.keys()), list(roles.keys())
        assert 'Member' in list(roles.keys()), list(roles.keys())
        assert roles['Developer']._id in roles['Admin'].roles
        assert roles['Member']._id in roles['Developer'].roles

        # There're 1 user assigned to project, represented by
        # relational (vs named) ProjectRole's
        assert len(roles) == M.ProjectRole.query.find(dict(
            project_id=c.project._id)).count() - 1

    def test_email_address_claimed_by_user(self):
        addr = M.EmailAddress(email='test_admin@domain.net',
                              claimed_by_user_id=c.user._id)
        c.user.disabled = True
        ThreadLocalORMSession.flush_all()
        assert addr.claimed_by_user() is None

    @td.with_user_project('test-admin')
    def test_user_projects_by_role(self):
        assert ({p.shortname for p in c.user.my_projects()} ==
                {'test', 'test2', 'u/test-admin', 'adobe-1', '--init--'})
        assert ({p.shortname for p in c.user.my_projects_by_role_name('Admin')} ==
                {'test', 'test2', 'u/test-admin', 'adobe-1', '--init--'})
        # Remove admin access from c.user to test2 project
        project = M.Project.query.get(shortname='test2')
        admin_role = M.ProjectRole.by_name('Admin', project)
        developer_role = M.ProjectRole.by_name('Developer', project)
        user_role = M.ProjectRole.by_user(c.user, project=project, upsert=True)
        user_role.roles.remove(admin_role._id)
        user_role.roles.append(developer_role._id)
        ThreadLocalORMSession.flush_all()
        g.credentials.clear()
        assert ({p.shortname for p in c.user.my_projects()} ==
                {'test', 'test2', 'u/test-admin', 'adobe-1', '--init--'})
        assert ({p.shortname for p in c.user.my_projects_by_role_name('Admin')} ==
                {'test', 'u/test-admin', 'adobe-1', '--init--'})

    @td.with_user_project('test-admin')
    def test_user_projects_unnamed(self):
        """
        Confirm that spurious ProjectRoles associating a user with
        a project to which they do not belong to any named group
        don't cause the user to count as a member of the project.
        """
        sub1 = M.Project.query.get(shortname='test/sub1')
        M.ProjectRole(
            user_id=c.user._id,
            project_id=sub1._id)
        ThreadLocalORMSession.flush_all()
        project_names = [p.shortname for p in c.user.my_projects()]
        assert 'test/sub1' not in project_names
        assert 'test' in project_names

    @patch.object(g, 'user_message_max_messages', 3)
    def test_check_sent_user_message_times(self):
        user1 = M.User.register(dict(username='test-user'), make_project=False)
        time1 = datetime.utcnow() - timedelta(minutes=30)
        time2 = datetime.utcnow() - timedelta(minutes=45)
        time3 = datetime.utcnow() - timedelta(minutes=70)
        user1.sent_user_message_times = [time1, time2, time3]
        assert user1.can_send_user_message()
        assert len(user1.sent_user_message_times) == 2
        user1.sent_user_message_times.append(
            datetime.utcnow() - timedelta(minutes=15))
        assert not user1.can_send_user_message()

    @td.with_user_project('test-admin')
    def test_user_track_active(self):
        # without this session flushing inside track_active raises Exception
        setup_functional_test()
        c.user = M.User.by_username('test-admin')

        assert c.user.last_access['session_date'] is None
        assert c.user.last_access['session_ip'] is None
        assert c.user.last_access['session_ua'] is None

        req = Mock(headers={'User-Agent': 'browser'}, remote_addr='addr')
        c.user.track_active(req)
        c.user = M.User.by_username(c.user.username)
        assert c.user.last_access['session_date'] is not None
        assert c.user.last_access['session_ip'] == 'addr'
        assert c.user.last_access['session_ua'] == 'browser'

        # ensure that session activity tracked with a whole-day granularity
        prev_date = c.user.last_access['session_date']
        c.user.track_active(req)
        c.user = M.User.by_username(c.user.username)
        assert c.user.last_access['session_date'] == prev_date
        yesterday = datetime.utcnow() - timedelta(1)
        c.user.last_access['session_date'] = yesterday
        session(c.user).flush(c.user)
        c.user.track_active(req)
        c.user = M.User.by_username(c.user.username)
        assert c.user.last_access['session_date'] > yesterday

        # ...or if IP or User Agent has changed
        req.remote_addr = 'new addr'
        c.user.track_active(req)
        c.user = M.User.by_username(c.user.username)
        assert c.user.last_access['session_ip'] == 'new addr'
        assert c.user.last_access['session_ua'] == 'browser'
        req.headers['User-Agent'] = 'new browser'
        c.user.track_active(req)
        c.user = M.User.by_username(c.user.username)
        assert c.user.last_access['session_ip'] == 'new addr'
        assert c.user.last_access['session_ua'] == 'new browser'

    def test_user_index(self):
        c.user.email_addresses = ['email1', 'email2']
        c.user.set_pref('email_address', 'email2')
        idx = c.user.index()
        assert idx['id'] == c.user.index_id()
        assert idx['title'] == 'User test-admin'
        assert idx['type_s'] == 'User'
        assert idx['username_s'] == 'test-admin'
        assert idx['email_addresses_t'] == 'email1 email2'
        assert idx['email_address_s'] == 'email2'
        assert 'last_password_updated_dt' in idx
        assert idx['disabled_b'] is False
        assert 'results_per_page_i' in idx
        assert 'email_format_s' in idx
        assert 'disable_user_messages_b' in idx
        assert idx['display_name_t'] == 'Test Admin'
        assert idx['sex_s'] == 'Unknown'
        assert 'birthdate_dt' in idx
        assert 'localization_s' in idx
        assert 'timezone_s' in idx
        assert 'socialnetworks_t' in idx
        assert 'telnumbers_t' in idx
        assert 'skypeaccount_s' in idx
        assert 'webpages_t' in idx
        assert 'skills_t' in idx
        assert 'last_access_login_date_dt' in idx
        assert 'last_access_login_ip_s' in idx
        assert 'last_access_login_ua_t' in idx
        assert 'last_access_session_date_dt' in idx
        assert 'last_access_session_ip_s' in idx
        assert 'last_access_session_ua_t' in idx
        # provided bby auth provider
        assert 'user_registration_date_dt' in idx

    def test_user_index_none_values(self):
        c.user.email_addresses = [None]
        c.user.set_pref('telnumbers', [None])
        c.user.set_pref('webpages', [None])
        idx = c.user.index()
        assert idx['email_addresses_t'] == ''
        assert idx['telnumbers_t'] == ''
        assert idx['webpages_t'] == ''

    def test_user_backfill_login_details(self):
        with h.push_config(r, user_agent='TestBrowser/55'):
            # these shouldn't match
            h.auditlog_user('something happened')
            h.auditlog_user('blah blah Password changed')
        with h.push_config(r, user_agent='TestBrowser/56'):
            # these should all match, but only one entry created for this ip/ua
            h.auditlog_user('Account activated')
            h.auditlog_user('Successful login')
            h.auditlog_user('Password changed')
        with h.push_config(r, user_agent='TestBrowser/57'):
            # this should match too
            h.auditlog_user('Set up multifactor TOTP')
        ThreadLocalORMSession.flush_all()

        auth_provider = plugin.AuthenticationProvider.get(None)
        c.user.backfill_login_details(auth_provider)

        details = M.UserLoginDetails.query.find({'user_id': c.user._id}).sort('ua').all()
        assert len(details) == 2, details
        assert details[0].ip == '127.0.0.1'
        assert details[0].ua == 'TestBrowser/56'
        assert details[1].ip == '127.0.0.1'
        assert details[1].ua == 'TestBrowser/57'


class TestAuditLog:

    @classmethod
    def setup_class(cls):
        setup_basic_test()
        setup_global_objects()

    def test_message_html(self):
        al = h.auditlog_user('our message <script>alert(1)</script>')
        assert al.message == textwrap.dedent('''\
            IP Address: 127.0.0.1
            User-Agent: None
            our message <script>alert(1)</script>''')
        assert al.message_html == textwrap.dedent('''\
            IP Address: 127.0.0.1<br>
            User-Agent: None<br>
            <strong>our message &lt;script&gt;alert(1)&lt;/script&gt;</strong>''')
