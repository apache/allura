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

from tg import tmpl_context as c
import pytest

from ming.odm import ThreadLocalODMSession
from allura.tests import decorators as td
from allura.tests import TestController

from allura.lib.security import Credentials, all_allowed, has_access
from allura import model as M
from forgewiki import model as WM
from allura.lib.security import HIBPClientError, HIBPClient
from mock import Mock, patch
from requests.exceptions import Timeout


def _allow(obj, role, perm):
    obj.acl.insert(0, M.ACE.allow(role._id, perm))
    ThreadLocalODMSession.flush_all()
    Credentials.get().clear()


def _deny(obj, role, perm):
    obj.acl.insert(0, M.ACE.deny(role._id, perm))
    ThreadLocalODMSession.flush_all()
    Credentials.get().clear()


def _add_to_group(user, role):
    M.ProjectRole.by_user(user, upsert=True).roles.append(role._id)
    ThreadLocalODMSession.flush_all()
    Credentials.get().clear()


@patch('allura.lib.security.requests.get', side_effect=Timeout())
def test_check_breached_password(r_get):
    with pytest.raises(HIBPClientError):
        HIBPClient.check_breached_password('qwerty')


class TestSecurity(TestController):

    validate_skip = True

    @td.with_wiki
    def test_anon(self):
        self.app.get('/security/*anonymous/forbidden', status=302)
        self.app.get('/security/*anonymous/needs_auth', status=302)
        self.app.get('/security/*anonymous/needs_project_access_fail',
                     status=302)
        self.app.get(
            '/security/*anonymous/needs_artifact_access_fail', status=302)

    @td.with_wiki
    def test_auth(self):
        self.app.get('/security/test-admin/forbidden', status=403)
        self.app.get('/security/test-admin/needs_auth', status=200)
        self.app.get('/security/test-admin/needs_project_access_fail',
                     status=403)
        self.app.get('/security/test-admin/needs_project_access_ok',
                     status=200)
        # This should fail b/c test-user doesn't have the permission
        self.app.get('/security/test-user/needs_artifact_access_fail',
                     extra_environ=dict(username='test-user'), status=403)
        # This should succeed b/c users with the 'admin' permission on a
        # project implicitly have all permissions to everything in the project
        self.app.get(
            '/security/test-admin/needs_artifact_access_fail', status=200)
        self.app.get('/security/test-admin/needs_artifact_access_ok',
                     status=200)

    @td.with_wiki
    def test_all_allowed(self):
        wiki = c.project.app_instance('wiki')
        admin_role = M.ProjectRole.by_name('Admin')
        dev_role = M.ProjectRole.by_name('Developer')
        member_role = M.ProjectRole.by_name('Member')
        auth_role = M.ProjectRole.by_name('*authenticated')
        anon_role = M.ProjectRole.by_name('*anonymous')
        test_user = M.User.by_username('test-user')

        assert all_allowed(wiki, admin_role) == {
            'configure', 'read', 'create', 'edit', 'unmoderated_post', 'post', 'moderate', 'admin', 'delete'}
        assert all_allowed(wiki, dev_role) == {
            'read', 'create', 'edit', 'unmoderated_post', 'post', 'moderate', 'delete'}
        assert (all_allowed(wiki, member_role) ==
                {'read', 'create', 'edit', 'unmoderated_post', 'post'})
        assert (all_allowed(wiki, auth_role) ==
                {'read', 'post', 'unmoderated_post'})
        assert all_allowed(wiki, anon_role) == {'read'}
        assert (all_allowed(wiki, test_user) ==
                {'read', 'post', 'unmoderated_post'})

        _add_to_group(test_user, member_role)

        assert (all_allowed(wiki, test_user) ==
                {'read', 'create', 'edit', 'unmoderated_post', 'post'})

        _deny(wiki, auth_role, 'unmoderated_post')

        assert (all_allowed(wiki, member_role) ==
                {'read', 'create', 'edit', 'post'})
        assert (all_allowed(wiki, test_user) ==
                {'read', 'create', 'edit', 'post'})

    @td.with_wiki
    def test_deny_vs_allow(self):
        '''
        Test interaction of DENYs and ALLOWs in has_access.
        '''
        wiki = c.project.app_instance('wiki')
        page = WM.Page.query.get(app_config_id=wiki.config._id)
        anon_role = M.ProjectRole.by_name('*anonymous')
        auth_role = M.ProjectRole.by_name('*authenticated')
        test_user = M.User.by_username('test-user')

        # confirm that *anon has expected access
        assert has_access(page, 'read', anon_role)()
        assert has_access(page, 'post', anon_role)()
        assert has_access(page, 'unmoderated_post', anon_role)()
        assert all_allowed(page, anon_role) == {'read'}
        # as well as an authenticated user
        assert has_access(page, 'read', test_user)()
        assert has_access(page, 'post', test_user)()
        assert has_access(page, 'unmoderated_post', test_user)()
        assert (all_allowed(page, test_user) ==
                {'read', 'post', 'unmoderated_post'})

        _deny(page, auth_role, 'read')

        # read granted to *anon should *not* bubble up past the *auth DENY
        assert not has_access(page, 'read', test_user)()
        # but other perms should not be affected
        assert has_access(page, 'post', test_user)()
        assert has_access(page, 'unmoderated_post', test_user)()
        # FIXME: all_allowed doesn't respect blocked user feature
        #assert_equal(all_allowed(page, test_user), set(['post', 'unmoderated_post']))

        assert has_access(wiki, 'read', test_user)()
        assert has_access(wiki, 'post', test_user)()
        assert has_access(wiki, 'unmoderated_post', test_user)()
        assert (all_allowed(wiki, test_user) ==
                {'read', 'post', 'unmoderated_post'})

        _deny(wiki, anon_role, 'read')
        _allow(wiki, auth_role, 'read')

        # there isn't a true heiarchy of roles, so any applicable DENY
        # will block a user, even if there's an explicit ALLOW "higher up"
        assert not has_access(wiki, 'read', test_user)()
        assert has_access(wiki, 'post', test_user)()
        assert has_access(wiki, 'unmoderated_post', test_user)()
        # FIXME: all_allowed doesn't respect blocked user feature
        #assert_equal(all_allowed(wiki, test_user), set(['post', 'unmoderated_post']))

    @td.with_wiki
    def test_implicit_project(self):
        '''
        Test that relying on implicit project context does the Right Thing.

        If you call has_access(artifact, perm), it should use the roles from
        the project to which artifact belongs, even in c.project is something
        else.  If you really want to use the roles from an unrelated project,
        you should have to be very explicit about it, not just set c.project.
        '''
        project1 = c.project
        project2 = M.Project.query.get(shortname='test2')
        wiki = project1.app_instance('wiki')
        page = WM.Page.query.get(app_config_id=wiki.config._id)
        test_user = M.User.by_username('test-user')

        assert project1.shortname == 'test'
        assert has_access(page, 'read', test_user)()
        c.project = project2
        assert has_access(page, 'read', test_user)()

    @td.with_wiki
    def test_deny_access_for_single_user(self):
        wiki = c.project.app_instance('wiki')
        user = M.User.by_username('test-user')
        assert has_access(wiki, 'read', user)()
        wiki.acl.append(
            M.ACE.deny(M.ProjectRole.by_user(user, upsert=True)._id, 'read', 'Spammer'))
        Credentials.get().clear()
        assert not has_access(wiki, 'read', user)()
