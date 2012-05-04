from mock import patch
from tg import config

from nose.tools import assert_equal

from alluratest.controller import TestController
from allura.tests import decorators as td


class TestActivityController(TestController):
    def setUp(self, *args, **kwargs):
        super(TestActivityController, self).setUp(*args, **kwargs)
        self._enabled = config.get('activitystream.enabled', 'false')
        config['activitystream.enabled'] = 'true'

    def tearDown(self, *args, **kwargs):
        super(TestActivityController, self).tearDown(*args, **kwargs)
        config['activitystream.enabled'] = self._enabled

    def test_index(self):
        resp = self.app.get('/activity/')
        assert 'No activity to display.' in resp

    def test_index_disabled(self):
        config['activitystream.enabled'] = 'false'
        resp = self.app.get('/activity/', status=404)

    def test_index_override(self):
        config['activitystream.enabled'] = 'false'
        self.app.cookies['activitystream.enabled'] = 'true'
        resp = self.app.get('/activity/')
        assert 'No activity to display.' in resp

    @td.with_tool('u/test-admin', 'activity')
    @td.with_user_project('test-admin')
    @patch('forgeactivity.main.g._director')
    def test_viewing_own_user_project(self, director):
        resp = self.app.get('/u/test-admin/activity/')
        assert director.create_timeline.call_count == 1
        assert director.create_timeline.call_args[0][0].username == 'test-admin'
