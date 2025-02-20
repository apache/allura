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
import formencode as fe
from mock import Mock, patch

from allura import model as M
from allura.lib import validators as v
from allura.lib.decorators import task
from alluratest.controller import setup_basic_test
from allura.websetup.bootstrap import create_user


def _setup_method():
    setup_basic_test()


@task
def dummy_task(*args, **kw):
    pass


class TestJsonConverter:
    val = v.JsonConverter

    def setup_method(self, method):
        _setup_method()

    def test_valid(self):
        assert {} == self.val.to_python('{}')

    def test_invalid(self):
        with pytest.raises(fe.Invalid):
            self.val.to_python('{')
        with pytest.raises(fe.Invalid):
            self.val.to_python('3')


class TestJsonFile:

    def setup_method(self, method):
        _setup_method()

    val = v.JsonFile

    class FieldStorage:

        def __init__(self, content):
            self.value = content

    def test_valid(self):
        assert {} == self.val.to_python(self.FieldStorage('{}'))

    def test_invalid(self):
        with pytest.raises(fe.Invalid):
            self.val.to_python(self.FieldStorage('{'))


class TestUserMapFile:
    val = v.UserMapJsonFile()

    def setup_method(self, method):
        _setup_method()

    class FieldStorage:

        def __init__(self, content):
            self.value = content

    def test_valid(self):
        assert {"user_old": "user_new"} == self.val.to_python(
            self.FieldStorage('{"user_old": "user_new"}'))

    def test_invalid(self):
        with pytest.raises(fe.Invalid):
            self.val.to_python(self.FieldStorage('{"user_old": 1}'))

    def test_as_string(self):
        val = v.UserMapJsonFile(as_string=True)
        assert '{"user_old": "user_new"}' == val.to_python(
            self.FieldStorage('{"user_old": "user_new"}'))


class TestUserValidator:
    val = v.UserValidator

    def setup_method(self, method):
        _setup_method()

    def test_valid(self):
        assert M.User.by_username('root') == self.val.to_python('root')

    def test_invalid(self):
        with pytest.raises(fe.Invalid) as cm:
            self.val.to_python('fakeuser')
        assert str(cm.value) == "Invalid username"


class TestAnonymousValidator:
    val = v.AnonymousValidator

    def setup_method(self, method):
        _setup_method()

    @patch('allura.lib.validators.c')
    def test_valid(self, c):
        c.user = M.User.by_username('root')
        assert self.val.to_python(True)

    @patch('allura.lib.validators.c')
    def test_invalid(self, c):
        c.user = M.User.anonymous()
        with pytest.raises(fe.Invalid) as cm:
            self.val.to_python(True)
        assert str(cm.value) == "Log in to Mark as Private"


class TestMountPointValidator:

    def setup_method(self, method):
        _setup_method()

    @patch('allura.lib.validators.c')
    def test_valid(self, c):
        App = Mock()
        App.relaxed_mount_points = False
        App.validate_mount_point.return_value = True
        c.project.app_instance.return_value = None
        val = v.MountPointValidator(App)
        assert 'mymount' == val.to_python('Mymount')

    @patch('allura.lib.validators.c')
    def test_invalid(self, c):
        App = Mock()
        App.relaxed_mount_points = False
        App.validate_mount_point.return_value = False
        c.project.app_instance.return_value = False
        val = v.MountPointValidator(App)
        with pytest.raises(fe.Invalid):
            val.to_python('mymount')

    @patch('allura.lib.validators.c')
    def test_relaxed_mount_points(self, c):
        App = Mock()
        App.relaxed_mount_points = True
        App.validate_mount_point.return_value = True
        c.project.app_instance.return_value = None
        val = v.MountPointValidator(App)
        assert 'Mymount' == val.to_python('Mymount')

    @patch('allura.lib.validators.c')
    def test_in_use(self, c):
        App = Mock()
        App.relaxed_mount_points = False
        App.validate_mount_point.return_value = True
        c.project.app_instance.return_value = True
        val = v.MountPointValidator(App)
        with pytest.raises(fe.Invalid):
            val.to_python('mymount')

    @patch('allura.lib.validators.c')
    def test_reserved(self, c):
        App = Mock()
        App.relaxed_mount_points = False
        App.validate_mount_point.return_value = True
        c.project.app_instance.return_value = False
        val = v.MountPointValidator(App)
        with pytest.raises(fe.Invalid):
            val.to_python('feed')

    @patch('allura.lib.validators.c')
    def test_empty(self, c):
        App = Mock()
        App.default_mount_point = 'wiki'
        c.project.app_instance.side_effect = lambda mp: None if mp != 'wiki' else True
        val = v.MountPointValidator(App)
        assert 'wiki-0' == val.to_python('')
        assert 'wiki-0' == val.to_python(None)


class TestTaskValidator:
    val = v.TaskValidator

    def setup_method(self, method):
        _setup_method()

    def test_valid(self):
        assert dummy_task == self.val.to_python('allura.tests.test_validators.dummy_task')

    def test_invalid_name(self):
        with pytest.raises(fe.Invalid) as cm:
            self.val.to_python('badname')
        assert str(cm.value).startswith('Invalid task name')

    def test_import_failure(self):
        with pytest.raises(fe.Invalid) as cm:
            self.val.to_python('allura.does.not.exist')
        assert str(cm.value) == 'Could not import "allura.does.not.exist"'

    def test_attr_lookup_failure(self):
        with pytest.raises(fe.Invalid) as cm:
            self.val.to_python('allura.tests.test_validators.typo')
        assert str(cm.value) == 'Module has no attribute "typo"'

    def test_not_a_task(self):
        with pytest.raises(fe.Invalid) as cm:
            self.val.to_python('allura.tests.test_validators._setup_method')
        assert str(cm.value) == '"allura.tests.test_validators._setup_method" is not a task.'


class TestPathValidator:
    val = v.PathValidator(strip=True, if_missing={}, if_empty={})

    def setup_method(self, method):
        _setup_method()

    def test_valid_project(self):
        project = M.Project.query.get(shortname='test')
        d = self.val.to_python('/p/test')
        assert d['project'] == project
        assert 'app' not in d

    def test_project_in_nbhd_with_prefix(self):
        create_user('myuser', make_project=True)
        project = M.Project.query.get(shortname='u/myuser')
        d = self.val.to_python('/u/myuser')
        assert d['project'] == project
        assert 'app' not in d

    def test_valid_app(self):
        project = M.Project.query.get(shortname='test')
        app = project.app_instance('admin')
        d = self.val.to_python('/p/test/admin/')
        assert d['project'] == project
        assert d['app'].config._id == app.config._id

    def test_invalid_format(self):
        with pytest.raises(fe.Invalid) as cm:
            self.val.to_python('test')
        assert str(cm.value).startswith(
            'You must specify at least a neighborhood and project')

    def test_invalid_neighborhood(self):
        with pytest.raises(fe.Invalid) as cm:
            self.val.to_python('/q/test')
        assert str(cm.value) == 'Invalid neighborhood: /q/'

    def test_invalid_project(self):
        with pytest.raises(fe.Invalid) as cm:
            self.val.to_python('/p/badproject')
        assert str(cm.value) == 'Invalid project: badproject'

    def test_invalid_app_mount_point(self):
        with pytest.raises(fe.Invalid) as cm:
            self.val.to_python('/p/test/badapp')
        assert str(cm.value) == 'Invalid app mount point: badapp'

    def test_no_input(self):
        assert {} == self.val.to_python('')


class TestUrlValidator:
    val = v.URL

    def setup_method(self, method):
        _setup_method()

    def test_valid(self):
        assert 'http://192.168.0.1' == self.val.to_python('192.168.0.1')
        assert 'http://url' == self.val.to_python('url')

    def test_invalid_ip(self):
        with pytest.raises(fe.Invalid) as cm:
            self.val.to_python('192.168.0')
        assert str(cm.value) == 'That is not a valid URL'

    def test_invalid_url(self):
        with pytest.raises(fe.Invalid) as cm:
            self.val.to_python('u"rl')
        assert str(cm.value) == 'That is not a valid URL'


class TestNonHttpUrlValidator:
    val = v.NonHttpUrl

    def setup_method(self, method):
        _setup_method()

    def test_valid(self):
        assert 'svn://192.168.0.1' == self.val.to_python('svn://192.168.0.1')
        assert 'ssh+git://url' == self.val.to_python('ssh+git://url')

    def test_invalid(self):
        with pytest.raises(fe.Invalid) as cm:
            self.val.to_python('http://u"rl')
        assert str(cm.value) == 'That is not a valid URL'

    def test_no_scheme(self):
        with pytest.raises(fe.Invalid) as cm:
            self.val.to_python('url')
        assert str(cm.value) == 'You must start your URL with a scheme'


class TestIconValidator:
    val = v.IconValidator

    def _mock(self, val):
        # Mock has an attr `mixed`, which inadvertantly gets called by formencode to_python method :/
        def f(filename): pass

        m = Mock(spec=f)
        m.filename = val
        return m

    def test_valid(self):
        input = self._mock('foo.png')
        assert input == self.val.to_python(input)

        input = self._mock('foo.jpg')
        assert input == self.val.to_python(input)

        input = self._mock('svg.jpg')
        assert input == self.val.to_python(input)

    def test_invalid(self):
        input = self._mock('foo.svg')
        with pytest.raises(fe.Invalid) as cm:
            self.val.to_python(input)
        assert str(cm.value) == 'Project icons must be PNG, GIF, JPG, or BMP format.'

        input = self._mock('foogif.svg')
        with pytest.raises(fe.Invalid) as cm:
            assert input == self.val.to_python(input)
        assert str(cm.value) == 'Project icons must be PNG, GIF, JPG, or BMP format.'
