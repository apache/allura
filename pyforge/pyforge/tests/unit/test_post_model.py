from pyforge.tests.unit import WithDatabase
from pyforge.tests.unit import patches
from pyforge.tests.unit.factories import create_post


class TestPostModel(WithDatabase):
    patches = [patches.fake_app_patch,
               patches.disable_notifications_patch]

    def setUp(self):
        super(TestPostModel, self).setUp()
        self.post = create_post('mypost')

    def test_that_it_is_pending_by_default(self):
        assert self.post.status == 'pending'

    def test_that_it_can_be_approved(self):
        self.post.approve()
        assert self.post.status == 'ok'

