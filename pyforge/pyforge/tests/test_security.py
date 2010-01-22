from pyforge.tests import TestController

app = None

class TestSecurity(TestController):

    def test_security(self):
        self.app.get('/security/*anonymous/forbidden', status=401)
        self.app.get('/security/test_admin/forbidden', status=403)
        self.app.get('/security/*anonymous/needs_auth', status=401)
        self.app.get('/security/test_admin/needs_auth', status=200)
        self.app.get('/security/*anonymous/needs_project_access_fail', status=401)
        self.app.get('/security/test_admin/needs_project_access_fail', status=403)
        self.app.get('/security/*anonymous/needs_project_access_ok', status=200)
        self.app.get('/security/test_admin/needs_project_access_ok', status=200)
        self.app.get('/security/*anonymous/needs_artifact_access_fail', status=401)
        self.app.get('/security/test_admin/needs_artifact_access_fail', status=403)
        self.app.get('/security/*anonymous/needs_artifact_access_ok', status=200)
        self.app.get('/security/test_admin/needs_artifact_access_ok', status=200)



