import mock

from tg import config
from nose.tools import assert_equals, assert_true
from ming.orm import session
from bson.objectid import ObjectId

from allura import model as M
from allura.lib import helpers as h
from allura.tests import TestController


class TestTroveCategory(TestController):

    @mock.patch('allura.model.project.g.post_event')
    def test_events(self, post_event):
        # Create event
        cfg = {'trovecategories.enableediting': 'true'}
        with h.push_config(config, **cfg):
            r = self.app.post('/categories/create/', params=dict(categoryname='test'))

        category_id = post_event.call_args[0][1]
        assert_true(isinstance(category_id, ObjectId))
        assert_equals(post_event.call_args[0][0], 'trove_category_created')
        category = M.TroveCategory.query.get(_id=category_id)

        # Update event
        category.fullname = 'test2'
        session(M.TroveCategory).flush()
        edited_category_id = post_event.call_args[0][1]
        assert_true(isinstance(edited_category_id, ObjectId))
        assert_equals(edited_category_id, category_id)
        assert_equals(post_event.call_args[0][0], 'trove_category_updated')

        # Delete event
        M.TroveCategory.delete(category)
        session(M.TroveCategory).flush()
        deleted_category_id = post_event.call_args[0][1]
        assert_true(isinstance(deleted_category_id, ObjectId))
        assert_equals(deleted_category_id, category_id)
        assert_equals(post_event.call_args[0][0], 'trove_category_deleted')        

    def test_enableediting_setting(self):
        def check_access(username=None, status=None):
            self.app.get('/categories/', status=status,
                         extra_environ=dict(username=username))

        cfg = {'trovecategories.enableediting': 'true'}

        with h.push_config(config, **cfg):
            check_access(username='test-user', status=200)
            check_access(username='root', status=200)

        cfg['trovecategories.enableediting'] = 'false'
        with h.push_config(config, **cfg):
            check_access(username='test-user', status=403)
            check_access(username='root', status=403)

        cfg['trovecategories.enableediting'] = 'admin'
        with h.push_config(config, **cfg):
            check_access(username='test-user', status=403)
            check_access(username='root', status=200)
