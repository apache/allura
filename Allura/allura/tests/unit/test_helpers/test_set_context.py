from nose.tools import assert_raises
from pylons import c

from allura.lib.helpers import set_context
from allura.lib.exceptions import NoSuchProjectError, NoSuchNeighborhoodError
from allura.tests.unit import WithDatabase
from allura.tests.unit import patches
from allura.tests.unit.factories import (create_project,
                                          create_app_config,
                                          create_neighborhood)
from allura.model.project import Neighborhood


class TestWhenProjectIsFoundAndAppIsNot(WithDatabase):
    def setUp(self):
        super(TestWhenProjectIsFoundAndAppIsNot, self).setUp()
        self.myproject = create_project('myproject')
        set_context('myproject', neighborhood=self.myproject.neighborhood)

    def test_that_it_sets_the_project(self):
        assert c.project is self.myproject

    def test_that_it_sets_the_app_to_none(self):
        assert c.app is None, c.app


class TestWhenProjectIsFoundInNeighborhood(WithDatabase):
    def setUp(self):
        super(TestWhenProjectIsFoundInNeighborhood, self).setUp()
        self.myproject = create_project('myproject')
        set_context('myproject', neighborhood=self.myproject.neighborhood)

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
        set_context('myproject', app_config_id=self.app_config._id, neighborhood=self.myproject.neighborhood)

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
        set_context('myproject', mount_point='my_mounted_app', neighborhood=self.myproject.neighborhood)

    def test_that_it_sets_the_app(self):
        assert c.app is self.fake_app

    def test_that_it_gets_the_app_by_its_mount_point(self):
        self.project_app_instance_function.assert_called_with(
            'my_mounted_app')


class TestWhenProjectIsNotFound(WithDatabase):

    def test_that_it_raises_an_exception(self):
        nbhd = create_neighborhood()
        assert_raises(NoSuchProjectError,
                      set_context,
                      'myproject',
                      neighborhood=nbhd)

class TestWhenNeighborhoodIsNotFound(WithDatabase):

    def test_that_it_raises_an_exception(self):
        assert_raises(NoSuchNeighborhoodError,
                      set_context,
                      'myproject',
                      neighborhood='myneighborhood')
