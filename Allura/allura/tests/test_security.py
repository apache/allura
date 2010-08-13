from allura.tests import TestController

class TestSecurity(TestController):

    def test_anon(self):
        self.app.get('/security/*anonymous/forbidden', status=302)
        self.app.get('/security/*anonymous/needs_auth', status=302)
        self.app.get('/security/*anonymous/needs_project_access_fail', status=302)
        self.app.get('/security/*anonymous/needs_artifact_access_fail', status=302)

    def test_auth(self):
        self.app.get('/security/test-admin/forbidden', status=403)
        self.app.get('/security/test-admin/needs_auth', status=200)
        self.app.get('/security/test-admin/needs_project_access_fail', status=403)
        self.app.get('/security/test-admin/needs_project_access_ok', status=200)
        self.app.get('/security/test-admin/needs_artifact_access_fail', status=403)
        self.app.get('/security/test-admin/needs_artifact_access_ok', status=200)



