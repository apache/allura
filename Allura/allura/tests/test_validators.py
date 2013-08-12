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

from allura import model as M
from allura.lib import validators as v
from allura.lib.decorators import task
from alluratest.controller import setup_basic_test


def setUp():
    setup_basic_test()


@task
def dummy_task(*args, **kw):
    pass


class TestJsonConverter(unittest.TestCase):
    val = v.JsonConverter

    def test_valid(self):
        self.assertEqual({}, self.val.to_python('{}'))

    def test_invalid(self):
        with self.assertRaises(fe.Invalid):
            self.val.to_python('{')


class TestJsonFile(unittest.TestCase):
    val = v.JsonFile

    class FieldStorage(object):
        def __init__(self, content):
            self.value = content

    def test_valid(self):
        self.assertEqual({}, self.val.to_python(self.FieldStorage('{}')))

    def test_invalid(self):
        with self.assertRaises(fe.Invalid):
            self.val.to_python(self.FieldStorage('{'))


class TestUserMapFile(unittest.TestCase):
    val = v.UserMapJsonFile()

    class FieldStorage(object):
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

    def test_valid(self):
        self.assertEqual(M.User.by_username('root'), self.val.to_python('root'))

    def test_invalid(self):
        with self.assertRaises(fe.Invalid) as cm:
            self.val.to_python('fakeuser')
        self.assertEqual(str(cm.exception), "Invalid username")


class TestTaskValidator(unittest.TestCase):
    val = v.TaskValidator

    def test_valid(self):
        self.assertEqual(dummy_task, self.val.to_python('allura.tests.test_validators.dummy_task'))

    def test_invalid_name(self):
        with self.assertRaises(fe.Invalid) as cm:
            self.val.to_python('badname')
        self.assertTrue(str(cm.exception).startswith('Invalid task name'))

    def test_import_failure(self):
        with self.assertRaises(fe.Invalid) as cm:
            self.val.to_python('allura.does.not.exist')
        self.assertEqual(str(cm.exception), 'Could not import "allura.does.not.exist"')

    def test_attr_lookup_failure(self):
        with self.assertRaises(fe.Invalid) as cm:
            self.val.to_python('allura.tests.test_validators.typo')
        self.assertEqual(str(cm.exception), 'Module has no attribute "typo"')

    def test_not_a_task(self):
        with self.assertRaises(fe.Invalid) as cm:
            self.val.to_python('allura.tests.test_validators.setUp')
        self.assertEqual(str(cm.exception), '"allura.tests.test_validators.setUp" is not a task.')


class TestPathValidator(unittest.TestCase):
    val = v.PathValidator(strip=True, if_missing={}, if_empty={})

    def test_valid_project(self):
        project = M.Project.query.get(shortname='test')
        d = self.val.to_python('/p/test')
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
