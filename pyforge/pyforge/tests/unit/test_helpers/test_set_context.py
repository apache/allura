from nose.tools import assert_raises
from pylons import c

from pyforge.lib.helpers import set_context, NoSuchProjectError
from pyforge.tests.unit import WithDatabase
from pyforge.tests.unit import patches
from pyforge.tests.unit.factories import (create_project,
                                          create_app_config)


class TestWhenProjectIsFoundAndAppIsNot(WithDatabase):
    def setUp(self):
        super(TestWhenProjectIsFoundAndAppIsNot, self).setUp()
        self.myproject = create_project('myproject')
        set_context('myproject')

    def test_that_it_sets_the_project(self):
        assert c.project is self.myproject

    def test_that_it_sets_the_app_to_none(self):
        assert c.app is None


class TestWhenAppIsFoundByID(WithDatabase):
    patches = [patches.project_app_loading_patch]

    def setUp(self):
        super(TestWhenAppIsFoundByID, self).setUp()
        self.myproject = create_project('myproject')
        self.app_config = create_app_config(self.myproject, 'my_mounted_app')
        set_context('myproject', app_config_id=self.app_config._id)

    def test_that_it_sets_the_app(self):
        assert c.app is self.fake_app

    def test_that_it_gets_the_app_by_its_app_config(self):
        self.project_app_instance_function.assert_called_with(self.app_config)


class TestWhenAppIsFoundByMountPoint(WithDatabase):
    patches = [patches.project_app_loading_patch]

    def setUp(self):
        super(TestWhenAppIsFoundByMountPoint, self).setUp()
        self.myproject = create_project('myproject')
        self.app_config = create_app_config(self.myproject, 'my_mounted_app')
        set_context('myproject', mount_point='my_mounted_app')

    def test_that_it_sets_the_app(self):
        assert c.app is self.fake_app

    def test_that_it_gets_the_app_by_its_mount_point(self):
        self.project_app_instance_function.assert_called_with(
            'my_mounted_app')


class TestWhenProjectIsNotFound(WithDatabase):
    patches = [patches.project_app_loading_patch]

    def test_that_it_raises_an_exception(self):
        assert_raises(NoSuchProjectError,
                      set_context,
                      'myproject')

