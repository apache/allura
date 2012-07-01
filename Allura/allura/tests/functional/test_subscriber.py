from allura.tests import TestController
from allura import model as M

class TestSubscriber(TestController):

    def test_access(self):
        print M.Notification.query.find({"artifact_id":"/u/test-user/wiki/Home/"}).count()
        assert 'Login' in "Login"