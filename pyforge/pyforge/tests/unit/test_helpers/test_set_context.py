from itertools import count

from mock import Mock, patch
from nose.tools import assert_raises

from pyforge.lib.helpers import set_context, NoSuchProjectError
from pyforge.tests.unit import WithDatabase
from pyforge.tests.unit.factories import (create_project,
                                          create_app_config)


def fake_c_patch(test_case):
    test_case.c = Mock()
    return patch('pyforge.lib.helpers.c', test_case.c)


def project_app_loading_patch(test_case):
    test_case.fake_app = Mock()
    test_case.project_app_instance_function = Mock()
    test_case.project_app_instance_function.return_value = test_case.fake_app

    return patch('pyforge.model.project.Project.app_instance',
                 test_case.project_app_instance_function)


class TestWhenProjectIsFoundAndAppIsNot(WithDatabase):
    patches = [fake_c_patch]

    def setUp(self):
        super(TestWhenProjectIsFoundAndAppIsNot, self).setUp()
        self.myproject = create_project('myproject')
        set_context('myproject')

    def test_that_it_sets_the_project(self):
        assert self.c.project is self.myproject

    def test_that_it_sets_the_app_to_none(self):
        assert self.c.app is None


class TestWhenAppIsFoundByID(WithDatabase):
    patches = [project_app_loading_patch, fake_c_patch]

    def setUp(self):
        super(TestWhenAppIsFoundByID, self).setUp()
        self.myproject = create_project('myproject')
        self.app_config = create_app_config(self.myproject, 'my_mounted_app')
        set_context('myproject', app_config_id=self.app_config._id)

    def test_that_it_sets_the_app(self):
        assert self.c.app is self.fake_app

    def test_that_it_gets_the_app_by_its_app_config(self):
        self.project_app_instance_function.assert_called_with(self.app_config)


class TestWhenAppIsFoundByMountPoint(WithDatabase):
    patches = [project_app_loading_patch, fake_c_patch]

    def setUp(self):
        super(TestWhenAppIsFoundByMountPoint, self).setUp()
        self.myproject = create_project('myproject')
        self.app_config = create_app_config(self.myproject, 'my_mounted_app')
        set_context('myproject', mount_point='my_mounted_app')

    def test_that_it_sets_the_app(self):
        assert self.c.app is self.fake_app

    def test_that_it_gets_the_app_by_its_mount_point(self):
        self.project_app_instance_function.assert_called_with(
            'my_mounted_app')


class TestWhenProjectIsNotFound(WithDatabase):
    patches = [project_app_loading_patch, fake_c_patch]

    def test_that_it_raises_an_exception(self):
        assert_raises(NoSuchProjectError,
                      set_context,
                      'myproject')

