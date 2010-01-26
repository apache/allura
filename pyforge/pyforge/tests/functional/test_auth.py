from pyforge.tests import TestController
from pyforge import model as M
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
                username='test_user', password='foo'))
        r = self.app.get('/auth/do_login', params=dict(
                username='test_user', password='food'),
                         status=401)
        r = self.app.get('/auth/do_login', params=dict(
                username='test_usera', password='foo'),
                         status=401)

    def test_prefs(self):
        r = self.app.get('/auth/prefs/')
        assert 'test@example.com' not in r
        r = self.app.post('/auth/prefs/update', params={
                'display_name':'Test Admin',
                'new_addr.addr':'test@example.com',
                'new_addr.claim':'Claim Address',
                'primary_addr':'Beta@wiki.test.projects.sourceforge.net',
                'preferences.email_format':'plain'})
        r = self.app.get('/auth/prefs/')
        assert 'test@example.com' in r
        r = self.app.post('/auth/prefs/update', params={
                'display_name':'Test Admin',
                'addr-1.ord':'1',
                'addr-2.ord':'1',
                'addr-2.delete':'on',
                'new_addr.addr':'',
                'primary_addr':'Beta@wiki.test.projects.sourceforge.net',
                'preferences.email_format':'plain'})
        r = self.app.get('/auth/prefs/')
        assert 'test@example.com' not in r
        ea = M.EmailAddress.query.get(_id='Beta@wiki.test.projects.sourceforge.net')
        ea.confirmed = True
        ThreadLocalORMSession.flush_all()
        r = self.app.post('/auth/prefs/update', params={
                'display_name':'Test Admin',
                'new_addr.addr':'Beta@wiki.test.projects.sourceforge.net',
                'new_addr.claim':'Claim Address',
                'primary_addr':'Beta@wiki.test.projects.sourceforge.net',
                'preferences.email_format':'plain'})
        r = self.app.get('/auth/prefs/')
        assert 'class="error"' in r


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
                username='test_admin', display_name='Test Admin'))
        r = self.app.post('/auth/do_setup_openid_user', params=dict(
                username='test_user', display_name='Test User'))
        r = self.app.post('/auth/do_setup_openid_user', params=dict(
                username='test_admin', display_name='Test Admin'))
        r = self.app.get('/auth/claim_oid')
        result = self.app.get('/auth/claim_verify_oid', params=dict(
                provider='http://www.google.com/accounts/o8/id', username='rick446@usa.net'))
        assert '<form' in result.body
        result = self.app.get('/auth/claim_verify_oid', params=dict(
                provider='', username='http://blog.pythonisito.com'))
        assert result.status_int == 302
