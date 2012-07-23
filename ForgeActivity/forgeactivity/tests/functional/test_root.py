import pylons
pylons.c = pylons.tmpl_context
pylons.g = pylons.app_globals
from pylons import c
from tg import config

from nose.tools import assert_equal

from alluratest.controller import TestController
from allura.lib.helpers import push_config


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
        assert 'Something happened.' in resp

    def test_index_disabled(self):
        config['activitystream.enabled'] = 'false'
        resp = self.app.get('/activity/', status=404)

    def test_index_override(self):
        config['activitystream.enabled'] = 'false'
        self.app.cookies['activitystream.enabled'] = 'true'
        resp = self.app.get('/activity/')
        assert 'Something happened.' in resp
