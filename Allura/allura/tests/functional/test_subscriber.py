from allura.tests import TestController
from allura.model import Notification,Post


class TestSubscriber(TestController):
    def _setUp(self):
        self.app.get("/wiki/")
        self.app.post(
            "/wiki/test_subscriber/update",
            params=dict(
                title="test_subscriber",
                text="Nothing much",
                labels="",
                labels_old=""))
        self.app.get("/wiki/test_subscriber/")

    def test_add_subscriber(self):
        response = self.app.get('/nf/admin/add_subscribers')
        print Notification.query.find().count()
        assert "<h1>Add Subscribers</h1>" in response
        #self.app.post("/nf/admin/add_subscribers",params=dict(Username="root",Url="http://localhost:8080/wiki/test_subscriber/"))
        assert 123 == Notification.query.find().count()
        assert 234 == Post.query.find().count()





