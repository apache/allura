from allura.tests import decorators as td
from allura.tests import TestController

class TestSecurity(TestController):

    validate_skip = True

    @td.with_wiki
    def test_anon(self):
        self.app.get('/security/*anonymous/forbidden', status=302)
        self.app.get('/security/*anonymous/needs_auth', status=302)
        self.app.get('/security/*anonymous/needs_project_access_fail', status=302)
        self.app.get('/security/*anonymous/needs_artifact_access_fail', status=302)

    @td.with_wiki
    def test_auth(self):
        self.app.get('/security/test-admin/forbidden', status=403)
        self.app.get('/security/test-admin/needs_auth', status=200)
        self.app.get('/security/test-admin/needs_project_access_fail', status=403)
        self.app.get('/security/test-admin/needs_project_access_ok', status=200)
        # This should fail b/c test-user doesn't have the permission
        self.app.get('/security/test-user/needs_artifact_access_fail', extra_environ=dict(username='test-user'), status=403)
        # This should succeed b/c users with the 'admin' permission on a
        # project implicitly have all permissions to everything in the project
        self.app.get('/security/test-admin/needs_artifact_access_fail', status=200)
        self.app.get('/security/test-admin/needs_artifact_access_ok', status=200)

