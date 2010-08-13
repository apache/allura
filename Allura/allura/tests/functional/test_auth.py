from allura.tests import TestController
from allura import model as M
from ming.orm.ormsession import ThreadLocalORMSession

class TestAuth(TestController):

    def test_login(self):
        result = self.app.get('/auth/')
        r = self.app.post('/auth/send_verification_link', params=dict(a='test@example.com'))
        r = self.app.post('/auth/send_verification_link', params=dict(a='Beta@wiki.test.projects.sourceforge.net'))
        ThreadLocalORMSession.flush_all()
        r = self.app.get('/auth/verify_addr', params=dict(a='foo'))
        r = self.app.get(r.location)
        assert 'class="error"' in r
        ea = M.EmailAddress.query.find().first()
        r = self.app.get('/auth/verify_addr', params=dict(a=ea.nonce))
        r = self.app.get(r.location)
        assert 'class="error"' not in r
        r = self.app.get('/auth/logout')
        r = self.app.get('/auth/do_login', params=dict(
                username='test-user', password='foo'))
        r = self.app.get('/auth/do_login', params=dict(
                username='test-user', password='food'),
                         status=302)
        r = self.app.get('/auth/do_login', params=dict(
                username='test-usera', password='foo'),
                         status=302)

    # def test_prefs(self):
    #     r = self.app.get('/auth/prefs/')
    #     assert 'test@example.com' not in r
    #     r = self.app.post('/auth/prefs/update', params={
    #             'display_name':'Test Admin',
    #             'new_addr.addr':'test@example.com',
    #             'new_addr.claim':'Claim Address',
    #             'primary_addr':'Beta@wiki.test.projects.sourceforge.net',
    #             'preferences.email_format':'plain'})
    #     r = self.app.get('/auth/prefs/')
    #     assert 'test@example.com' in r
    #     r = self.app.post('/auth/prefs/update', params={
    #             'display_name':'Test Admin',
    #             'addr-1.ord':'1',
    #             'addr-2.ord':'1',
    #             'addr-2.delete':'on',
    #             'new_addr.addr':'',
    #             'primary_addr':'Beta@wiki.test.projects.sourceforge.net',
    #             'preferences.email_format':'plain'})
    #     r = self.app.get('/auth/prefs/')
    #     assert 'test@example.com' not in r
    #     ea = M.EmailAddress.query.get(_id='Beta@wiki.test.projects.sourceforge.net')
    #     ea.confirmed = True
    #     ThreadLocalORMSession.flush_all()
    #     r = self.app.post('/auth/prefs/update', params={
    #             'display_name':'Test Admin',
    #             'new_addr.addr':'Beta@wiki.test.projects.sourceforge.net',
    #             'new_addr.claim':'Claim Address',
    #             'primary_addr':'Beta@wiki.test.projects.sourceforge.net',
    #             'preferences.email_format':'plain'})
    #     r = self.app.get('/auth/prefs/')
    #     assert 'class="error"' in r


    def test_openid(self):
        result = self.app.get('/auth/login_verify_oid', params=dict(
                provider='http://www.google.com/accounts/o8/id', username='rick446@usa.net'))
        assert '<form' in result.body
        result = self.app.get('/auth/login_verify_oid', params=dict(
                provider='http://www.google.com/accounts/', username='rick446@usa.net'),
                              status=302)
        result = self.app.get(result.location)
        assert 'class="error"' in result.body
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
        r = self.app.post('/auth/save_new', params=dict(username='aaa',password='123')).follow()
        assert 'Password must be at least 8 characters.' in r
        r = self.app.post('/auth/save_new', params=dict(username='aaa',
                                                        password='12345678',
                                                        display_name='Test Me',
                                                        open_ids='http://somewhere',
                                                        email_addresses='test@test.com')).follow()
        assert 'User "Test Me" registered' in r
        r = self.app.post('/auth/save_new', params=dict(username='aaa',password='12345678')).follow()
        assert 'That username is already taken. Please choose another.' in r

    def test_one_project_role(self):
        """Make sure when a user goes to a new project only one project role is created.
           There was an issue with extra project roles getting created if a user went directly to
           an admin page."""
        self.app.post('/auth/save_new', params=dict(username='aaa',
                                                        password='12345678',
                                                        display_name='Test Me',
                                                        open_ids='http://somewhere',
                                                        email_addresses='test@test.com')).follow()
        user = M.User.query.get(username='aaa')
        assert len(M.ProjectRole.query.find(dict(user_id=user._id)).all()) == 0
        self.app.get('/p/test/admin/perms',extra_environ=dict(username='aaa'))
        assert len(M.ProjectRole.query.find(dict(user_id=user._id)).all()) == 1
