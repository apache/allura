from allura.tests import TestController
from allura.tests import decorators as td
from allura.model.notification import Mailbox
from allura import model as M


class TestSubscriber(TestController):

    @td.with_user_project('test-admin')
    @td.with_wiki
    def test_add_subscriber(self):

        response = self.app.get("/nf/admin/add_subscribers")
        assert "<h1>Add Subscribers</h1>" in response

        response = self.app.get('/u/test-admin/profile/feed')
        assert 'Recent posts by Test Admin' in response
        assert '[test:wiki] test-admin created page Home' in response

        i = Mailbox.query.find().count()
        self.app.post("/nf/admin/add_subscribers", params=dict(
            for_user="root",
            artifact_url="http://localhost:8080/u/test-admin/wiki/Home/"))

        assert 1 == Mailbox.query.find(dict(
            user_id=M.User.by_username("root")._id,
            artifact_url="/u/test-admin/wiki/Home/")).count()
