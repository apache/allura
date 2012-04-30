import json

from datadiff.tools import assert_equal
from pylons import c
from allura.tests import TestController
from allura.tests import decorators as td
from allura import model as M
from ming.orm.ormsession import ThreadLocalORMSession


def unentity(s):
    return s.replace('&quot;', '"')

class TestAuth(TestController):

    def test_login(self):
        result = self.app.get('/auth/')
        r = self.app.post('/auth/send_verification_link', params=dict(a='test@example.com'))
        email = M.User.query.get(username='test-admin').email_addresses[0]
        r = self.app.post('/auth/send_verification_link', params=dict(a=email))
        ThreadLocalORMSession.flush_all()
        r = self.app.get('/auth/verify_addr', params=dict(a='foo'))
        assert json.loads(self.webflash(r))['status'] == 'error', self.webflash(r)
        ea = M.EmailAddress.query.find().first()
        r = self.app.get('/auth/verify_addr', params=dict(a=ea.nonce))
        assert json.loads(self.webflash(r))['status'] == 'ok', self.webflash(r)
        r = self.app.get('/auth/logout')
        r = self.app.post('/auth/do_login', params=dict(
                username='test-user', password='foo'))
        r = self.app.post('/auth/do_login', params=dict(
                username='test-user', password='food'))
        assert 'Invalid login' in str(r), r.showbrowser()
        r = self.app.post('/auth/do_login', params=dict(
                username='test-usera', password='foo'))
        assert 'Invalid login' in str(r), r.showbrowser()

    @td.with_user_project('test-admin')
    def test_prefs(self):
        r = self.app.get('/auth/prefs/', extra_environ=dict(username='test-admin'))
        assert 'test@example.com' not in r
        subscriptions = M.Mailbox.query.find(dict(user_id=c.user._id, is_flash=False)).all()
        # make sure page actually lists all the user's subscriptions
        assert len(subscriptions) > 0, 'Test user has no subscriptions, cannot verify that they are shown'
        for m in subscriptions:
            assert m._id in r, "Page doesn't list subscription for Mailbox._id = %s" % m._id
        r = self.app.post('/auth/prefs/update', params={
                 'display_name':'Test Admin',
                 'new_addr.addr':'test@example.com',
                 'new_addr.claim':'Claim Address',
                 'primary_addr':'test-admin@users.localhost',
                 'preferences.email_format':'plain'},
                extra_environ=dict(username='test-admin'))
        r = self.app.get('/auth/prefs/')
        assert 'test@example.com' in r
        r = self.app.post('/auth/prefs/update', params={
                 'display_name':'Test Admin',
                 'addr-1.ord':'1',
                 'addr-2.ord':'1',
                 'addr-2.delete':'on',
                 'new_addr.addr':'',
                 'primary_addr':'test-admin@users.localhost',
                 'preferences.email_format':'plain'},
                extra_environ=dict(username='test-admin'))
        r = self.app.get('/auth/prefs/')
        assert 'test@example.com' not in r
        ea = M.EmailAddress.query.get(_id='test-admin@users.localhost')
        ea.confirmed = True
        ThreadLocalORMSession.flush_all()
        r = self.app.post('/auth/prefs/update', params={
                 'display_name':'Test Admin',
                 'new_addr.addr':'test-admin@users.localhost',
                 'new_addr.claim':'Claim Address',
                 'primary_addr':'test-admin@users.localhost',
                 'preferences.email_format':'plain'},
                extra_environ=dict(username='test-admin'))

    def test_api_key(self):
         r = self.app.get('/auth/prefs/')
         assert 'No API token generated' in r
         r = self.app.post('/auth/prefs/gen_api_token', status=302)
         r = self.app.get('/auth/prefs/')
         assert 'No API token generated' not in r
         assert 'API Key:' in r
         assert 'Secret Key:' in r
         r = self.app.post('/auth/prefs/del_api_token', status=302)
         r = self.app.get('/auth/prefs/')
         assert 'No API token generated' in r

    def test_oauth(self):
         r = self.app.get('/auth/oauth/')
         r = self.app.post('/auth/oauth/register', params={'application_name': 'oautstapp', 'application_description': 'Oauth rulez'}).follow()
         assert 'oautstapp' in r
         r = self.app.post('/auth/oauth/delete').follow()
         assert 'Invalid app ID' in r

    def test_openid(self):
        result = self.app.get('/auth/login_verify_oid', params=dict(
                provider='http://www.google.com/accounts/o8/id', username='rick446@usa.net'))
        assert '<form' in result.body
        result = self.app.get('/auth/login_verify_oid', params=dict(
                provider='http://www.google.com/accounts/', username='rick446@usa.net'),
                              status=302)
        assert json.loads(self.webflash(result))['status'] == 'error', self.webflash(result)
        result = self.app.get('/auth/login_verify_oid', params=dict(
                provider='', username='http://blog.pythonisito.com'))
        assert result.status_int == 302
        r = self.app.get('/auth/setup_openid_user')
        r = self.app.post('/auth/do_setup_openid_user', params=dict(
                username='test-admin', display_name='Test Admin'))
        r = self.app.post('/auth/do_setup_openid_user', params=dict(
                username='test-user', display_name='Test User'))
        r = self.app.post('/auth/do_setup_openid_user', params=dict(
                username='test-admin', display_name='Test Admin'))
        r = self.app.get('/auth/claim_oid')
        result = self.app.get('/auth/claim_verify_oid', params=dict(
                provider='http://www.google.com/accounts/o8/id', username='rick446@usa.net'))
        assert '<form' in result.body
        result = self.app.get('/auth/claim_verify_oid', params=dict(
                provider='', username='http://blog.pythonisito.com'))
        assert result.status_int == 302

    def test_create_account(self):
        r = self.app.get('/auth/create_account')
        assert 'Create an Account' in r
        r = self.app.post('/auth/save_new', params=dict(username='aaa',pw='123'))
        assert 'Enter a value 8 characters long or more' in r
        r = self.app.post(
            '/auth/save_new',
            params=dict(
                username='aaa',
                pw='12345678',
                pw2='12345678',
                display_name='Test Me'))
        r = r.follow()
        assert 'User "Test Me" registered' in unentity(r.body)
        r = self.app.post(
            '/auth/save_new',
            params=dict(
                username='aaa',
                pw='12345678',
                pw2='12345678',
                display_name='Test Me'))
        assert 'That username is already taken. Please choose another.' in r
        r = self.app.get('/auth/logout')
        r = self.app.post(
            '/auth/do_login',
            params=dict(username='aaa', password='12345678'),
            status=302)

    def test_one_project_role(self):
        """Make sure when a user goes to a new project only one project role is created.
           There was an issue with extra project roles getting created if a user went directly to
           an admin page."""
        p_nbhd = M.Neighborhood.query.get(name='Projects')
        p = M.Project.query.get(shortname='test', neighborhood_id=p_nbhd._id)
        self.app.post('/auth/save_new', params=dict(
                username='aaa',
                pw='12345678',
                pw2='12345678',
                display_name='Test Me')).follow()
        user = M.User.query.get(username='aaa')
        assert M.ProjectRole.query.find(dict(user_id=user._id, project_id=p._id)).count() == 0
        r = self.app.get('/p/test/admin/permissions',extra_environ=dict(username='aaa'), status=403)
        assert M.ProjectRole.query.find(dict(user_id=user._id, project_id=p._id)).count() <= 1

    def test_default_lookup(self):
        # Make sure that default _lookup() throws 404
        self.app.get('/auth/foobar', status=404)

    @td.with_svn
    def test_refresh_repo(self):
        r = self.app.get('/auth/refresh_repo')
        assert_equal(r.body, 'No repo specified')

        r = self.app.get('/auth/refresh_repo/p/gbalksdfh')
        assert_equal(r.body, 'No project at /p/gbalksdfh')

        r = self.app.get('/auth/refresh_repo/p/test')
        assert_equal(r.body, '/p/test does not include a repo mount point')

        r = self.app.get('/auth/refresh_repo/p/test/blah/')
        assert_equal(r.body, 'Cannot find repo at /p/test/blah')

        r = self.app.get('/auth/refresh_repo/p/test/src/')
        assert_equal(r.body, '<Repository /tmp/svn/p/test/src> refresh queued.\n')

class TestUserPermissions(TestController):
    allow = dict(allow_read=True, allow_write=True, allow_create=True)
    read = dict(allow_read=True, allow_write=False, allow_create=False)
    disallow = dict(allow_read=False, allow_write=False, allow_create=False)

    def test_unknown_project(self):
        r = self._check_repo('/git/foo/bar', status=404)

    def test_unknown_app(self):
        r = self._check_repo('/git/test/bar')
        assert r == self.disallow, r

    @td.with_svn
    def test_repo_write(self):
        r = self._check_repo('/git/test/src.git')
        assert r == self.allow, r
        r = self._check_repo('/git/test/src')
        assert r == self.allow, r

    @td.with_svn
    def test_subdir(self):
        r = self._check_repo('/git/test/src.git/foo')
        assert r == self.allow, r
        r = self._check_repo('/git/test/src/foo')
        assert r == self.allow, r

    @td.with_svn
    def test_neighborhood(self):
        r = self._check_repo('/git/test.p/src.git')
        assert r == self.allow, r

    @td.with_svn
    def test_repo_read(self):
        r = self._check_repo(
            '/git/test.p/src.git',
            username='test-user')
        assert r == self.read, r

    def test_unknown_user(self):
        r = self._check_repo(
            '/git/test.p/src.git',
            username='test-usera',
            status=404)

    def _check_repo(self, path, username='test-admin', **kw):
        url = '/auth/repo_permissions'
        r = self.app.get(url, params=dict(
                repo_path=path,
                username=username), **kw)
        try:
            return r.json
        except:
            return r

    @td.with_repos
    def test_list_repos(self):
        r = self.app.get('/auth/repo_permissions', params=dict(username='test-admin'), status=200)
        assert_equal(json.loads(r.body), {"allow_write": [
            '/git/test/src-git',
            '/hg/test/src-hg',
            '/svn/test/src',
        ]})
