from allura.tests import TestController


class TestSubscriber(TestController):

    def test_add_subscriber(self):
        response = self.app.get('/nf/admin/add_subscribers')
        assert "<h1>Add Subscribers</h1>" in response
