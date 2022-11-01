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

import unittest
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


class TestJsonConverter(unittest.TestCase):
    val = v.JsonConverter

    def setup_method(self, method):
        _setup_method()

    def test_valid(self):
        self.assertEqual({}, self.val.to_python('{}'))

    def test_invalid(self):
        with self.assertRaises(fe.Invalid):
            self.val.to_python('{')
        with self.assertRaises(fe.Invalid):
            self.val.to_python('3')


class TestJsonFile(unittest.TestCase):

    def setup_method(self, method):
        _setup_method()

    val = v.JsonFile

    class FieldStorage:

        def __init__(self, content):
            self.value = content

    def test_valid(self):
        self.assertEqual({}, self.val.to_python(self.FieldStorage('{}')))

    def test_invalid(self):
        with self.assertRaises(fe.Invalid):
            self.val.to_python(self.FieldStorage('{'))


class TestUserMapFile(unittest.TestCase):
    val = v.UserMapJsonFile()

    def setup_method(self, method):
        _setup_method()

    class FieldStorage:

        def __init__(self, content):
            self.value = content

    def test_valid(self):
        self.assertEqual({"user_old": "user_new"}, self.val.to_python(
            self.FieldStorage('{"user_old": "user_new"}')))

    def test_invalid(self):
        with self.assertRaises(fe.Invalid):
            self.val.to_python(self.FieldStorage('{"user_old": 1}'))

    def test_as_string(self):
        val = v.UserMapJsonFile(as_string=True)
        self.assertEqual('{"user_old": "user_new"}', val.to_python(
            self.FieldStorage('{"user_old": "user_new"}')))


class TestUserValidator(unittest.TestCase):
    val = v.UserValidator

    def setup_method(self, method):
        _setup_method()

    def test_valid(self):
        self.assertEqual(M.User.by_username('root'),
                         self.val.to_python('root'))

    def test_invalid(self):
        with self.assertRaises(fe.Invalid) as cm:
            self.val.to_python('fakeuser')
        self.assertEqual(str(cm.exception), "Invalid username")


class TestAnonymousValidator(unittest.TestCase):
    val = v.AnonymousValidator

    def setup_method(self, method):
        _setup_method()

    @patch('allura.lib.validators.c')
    def test_valid(self, c):
        c.user = M.User.by_username('root')
        self.assertEqual(True, self.val.to_python(True))

    @patch('allura.lib.validators.c')
    def test_invalid(self, c):
        c.user = M.User.anonymous()
        with self.assertRaises(fe.Invalid) as cm:
            self.val.to_python(True)
        self.assertEqual(str(cm.exception), "Log in to Mark as Private")


class TestMountPointValidator(unittest.TestCase):

    def setup_method(self, method):
        _setup_method()

    @patch('allura.lib.validators.c')
    def test_valid(self, c):
        App = Mock()
        App.relaxed_mount_points = False
        App.validate_mount_point.return_value = True
        c.project.app_instance.return_value = None
        val = v.MountPointValidator(App)
        self.assertEqual('mymount', val.to_python('Mymount'))

    @patch('allura.lib.validators.c')
    def test_invalid(self, c):
        App = Mock()
        App.relaxed_mount_points = False
        App.validate_mount_point.return_value = False
        c.project.app_instance.return_value = False
        val = v.MountPointValidator(App)
        with self.assertRaises(fe.Invalid):
            val.to_python('mymount')

    @patch('allura.lib.validators.c')
    def test_relaxed_mount_points(self, c):
        App = Mock()
        App.relaxed_mount_points = True
        App.validate_mount_point.return_value = True
        c.project.app_instance.return_value = None
        val = v.MountPointValidator(App)
        self.assertEqual('Mymount', val.to_python('Mymount'))

    @patch('allura.lib.validators.c')
    def test_in_use(self, c):
        App = Mock()
        App.relaxed_mount_points = False
        App.validate_mount_point.return_value = True
        c.project.app_instance.return_value = True
        val = v.MountPointValidator(App)
        with self.assertRaises(fe.Invalid):
            val.to_python('mymount')

    @patch('allura.lib.validators.c')
    def test_reserved(self, c):
        App = Mock()
        App.relaxed_mount_points = False
        App.validate_mount_point.return_value = True
        c.project.app_instance.return_value = False
        val = v.MountPointValidator(App)
        with self.assertRaises(fe.Invalid):
            val.to_python('feed')

    @patch('allura.lib.validators.c')
    def test_empty(self, c):
        App = Mock()
        App.default_mount_point = 'wiki'
        c.project.app_instance.side_effect = lambda mp: None if mp != 'wiki' else True
        val = v.MountPointValidator(App)
        self.assertEqual('wiki-0', val.to_python(''))
        self.assertEqual('wiki-0', val.to_python(None))


class TestTaskValidator(unittest.TestCase):
    val = v.TaskValidator

    def setup_method(self, method):
        _setup_method()

    def test_valid(self):
        self.assertEqual(
            dummy_task, self.val.to_python('allura.tests.test_validators.dummy_task'))

    def test_invalid_name(self):
        with self.assertRaises(fe.Invalid) as cm:
            self.val.to_python('badname')
        self.assertTrue(str(cm.exception).startswith('Invalid task name'))

    def test_import_failure(self):
        with self.assertRaises(fe.Invalid) as cm:
            self.val.to_python('allura.does.not.exist')
        self.assertEqual(str(cm.exception),
                         'Could not import "allura.does.not.exist"')

    def test_attr_lookup_failure(self):
        with self.assertRaises(fe.Invalid) as cm:
            self.val.to_python('allura.tests.test_validators.typo')
        self.assertEqual(str(cm.exception), 'Module has no attribute "typo"')

    def test_not_a_task(self):
        with self.assertRaises(fe.Invalid) as cm:
            self.val.to_python('allura.tests.test_validators._setup_method')
        self.assertEqual(str(cm.exception),
                         '"allura.tests.test_validators._setup_method" is not a task.')


class TestPathValidator(unittest.TestCase):
    val = v.PathValidator(strip=True, if_missing={}, if_empty={})

    def setup_method(self, method):
        _setup_method()

    def test_valid_project(self):
        project = M.Project.query.get(shortname='test')
        d = self.val.to_python('/p/test')
        self.assertEqual(d['project'], project)
        self.assertTrue('app' not in d)

    def test_project_in_nbhd_with_prefix(self):
        create_user('myuser', make_project=True)
        project = M.Project.query.get(shortname='u/myuser')
        d = self.val.to_python('/u/myuser')
        self.assertEqual(d['project'], project)
        self.assertTrue('app' not in d)

    def test_valid_app(self):
        project = M.Project.query.get(shortname='test')
        app = project.app_instance('admin')
        d = self.val.to_python('/p/test/admin/')
        self.assertEqual(d['project'], project)
        self.assertEqual(d['app'].config._id, app.config._id)

    def test_invalid_format(self):
        with self.assertRaises(fe.Invalid) as cm:
            self.val.to_python('test')
        self.assertTrue(str(cm.exception).startswith(
            'You must specify at least a neighborhood and project'))

    def test_invalid_neighborhood(self):
        with self.assertRaises(fe.Invalid) as cm:
            self.val.to_python('/q/test')
        self.assertEqual(str(cm.exception), 'Invalid neighborhood: /q/')

    def test_invalid_project(self):
        with self.assertRaises(fe.Invalid) as cm:
            self.val.to_python('/p/badproject')
        self.assertEqual(str(cm.exception), 'Invalid project: badproject')

    def test_invalid_app_mount_point(self):
        with self.assertRaises(fe.Invalid) as cm:
            self.val.to_python('/p/test/badapp')
        self.assertEqual(str(cm.exception), 'Invalid app mount point: badapp')

    def test_no_input(self):
        self.assertEqual({}, self.val.to_python(''))


class TestUrlValidator(unittest.TestCase):
    val = v.URL

    def setup_method(self, method):
        _setup_method()

    def test_valid(self):
        self.assertEqual('http://192.168.0.1', self.val.to_python('192.168.0.1'))
        self.assertEqual('http://url', self.val.to_python('url'))

    def test_invalid_ip(self):
        with self.assertRaises(fe.Invalid) as cm:
            self.val.to_python('192.168.0')
        self.assertEqual(str(cm.exception), 'That is not a valid URL')

    def test_invalid_url(self):
        with self.assertRaises(fe.Invalid) as cm:
            self.val.to_python('u"rl')
        self.assertEqual(str(cm.exception), 'That is not a valid URL')


class TestNonHttpUrlValidator(unittest.TestCase):
    val = v.NonHttpUrl

    def setup_method(self, method):
        _setup_method()

    def test_valid(self):
        self.assertEqual('svn://192.168.0.1', self.val.to_python('svn://192.168.0.1'))
        self.assertEqual('ssh+git://url', self.val.to_python('ssh+git://url'))

    def test_invalid(self):
        with self.assertRaises(fe.Invalid) as cm:
            self.val.to_python('http://u"rl')
        self.assertEqual(str(cm.exception), 'That is not a valid URL')

    def test_no_scheme(self):
        with self.assertRaises(fe.Invalid) as cm:
            self.val.to_python('url')
        self.assertEqual(str(cm.exception), 'You must start your URL with a scheme')


class TestIconValidator(unittest.TestCase):
    val = v.IconValidator

    def _mock(self, val):
        # Mock has an attr `mixed`, which inadvertantly gets called by formencode to_python method :/
        def f(filename): pass

        m = Mock(spec=f)
        m.filename = val
        return m

    def test_valid(self):
        input = self._mock('foo.png')
        self.assertEqual(input, self.val.to_python(input))

        input = self._mock('foo.jpg')
        self.assertEqual(input, self.val.to_python(input))

        input = self._mock('svg.jpg')
        self.assertEqual(input, self.val.to_python(input))

    def test_invalid(self):
        input = self._mock('foo.svg')
        with self.assertRaises(fe.Invalid) as cm:
            self.val.to_python(input)
        self.assertEqual(str(cm.exception), 'Project icons must be PNG, GIF, JPG, or BMP format.')

        input = self._mock('foogif.svg')
        with self.assertRaises(fe.Invalid) as cm:
            self.assertEqual(input, self.val.to_python(input))
        self.assertEqual(str(cm.exception), 'Project icons must be PNG, GIF, JPG, or BMP format.')
