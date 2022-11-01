#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

import pytest
from tg import tmpl_context as c
from bson import ObjectId

from allura.lib.helpers import set_context
from allura.lib.exceptions import NoSuchProjectError, NoSuchNeighborhoodError
from allura.tests.unit import WithDatabase
from allura.tests.unit import patches
from allura.tests.unit.factories import (create_project,
                                         create_app_config,
                                         create_neighborhood)


class TestWhenProjectIsFoundAndAppIsNot(WithDatabase):

    def setup_method(self, method):
        super().setup_method(method)
        self.myproject = create_project('myproject')
        set_context('myproject', neighborhood=self.myproject.neighborhood)

    def test_that_it_sets_the_project(self):
        assert c.project is self.myproject

    def test_that_it_sets_the_app_to_none(self):
        assert c.app is None, c.app


class TestWhenProjectIsFoundInNeighborhood(WithDatabase):

    def setup_method(self, method):
        super().setup_method(method)
        self.myproject = create_project('myproject')
        set_context('myproject', neighborhood=self.myproject.neighborhood)

    def test_that_it_sets_the_project(self):
        assert c.project is self.myproject

    def test_that_it_sets_the_app_to_none(self):
        assert c.app is None


class TestWhenAppIsFoundByID(WithDatabase):
    patches = [patches.project_app_loading_patch]

    def setup_method(self, method):
        super().setup_method(method)
        self.myproject = create_project('myproject')
        self.app_config = create_app_config(self.myproject, 'my_mounted_app')
        set_context('myproject', app_config_id=self.app_config._id,
                    neighborhood=self.myproject.neighborhood)

    def test_that_it_sets_the_app(self):
        assert c.app is self.fake_app

    def test_that_it_gets_the_app_by_its_app_config(self):
        self.project_app_instance_function.assert_called_with(self.app_config)


class TestWhenAppIsFoundByMountPoint(WithDatabase):
    patches = [patches.project_app_loading_patch]

    def setup_method(self, method):
        super().setup_method(method)
        self.myproject = create_project('myproject')
        self.app_config = create_app_config(self.myproject, 'my_mounted_app')
        set_context('myproject', mount_point='my_mounted_app',
                    neighborhood=self.myproject.neighborhood)

    def test_that_it_sets_the_app(self):
        assert c.app is self.fake_app

    def test_that_it_gets_the_app_by_its_mount_point(self):
        self.project_app_instance_function.assert_called_with(
            'my_mounted_app')


class TestWhenProjectIsNotFound(WithDatabase):

    def test_that_it_raises_an_exception(self):
        nbhd = create_neighborhood()
        pytest.raises(NoSuchProjectError,
                      set_context,
                      'myproject',
                      neighborhood=nbhd)

    def test_proper_exception_when_id_lookup(self):
        create_neighborhood()
        pytest.raises(NoSuchProjectError,
                      set_context,
                      ObjectId(),
                      neighborhood=None)


class TestWhenNeighborhoodIsNotFound(WithDatabase):

    def test_that_it_raises_an_exception(self):
        pytest.raises(NoSuchNeighborhoodError,
                      set_context,
                      'myproject',
                      neighborhood='myneighborhood')
