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

from unittest import TestCase

from allura.app import Application
from allura import model
from allura.tests.unit import WithDatabase
from allura.tests.unit.patches import fake_app_patch
from allura.tests.unit.factories import create_project, create_app_config


class TestApplication(TestCase):

    def test_validate_mount_point(self):
        app = Application

        self.assertIsNotNone(app.validate_mount_point('dash-in-middle'))

        self.assertIsNone(app.validate_mount_point('end-dash-'))

        mount_point = '1.2+foo_bar'
        self.assertIsNone(app.validate_mount_point(mount_point))

        app.relaxed_mount_points = True
        self.assertIsNotNone(app.validate_mount_point(mount_point))

    def test_describe_permission(self):
        class DummyApp(Application):
            permissions_desc = {
                'foo': 'bar',
                'post': 'overridden',
            }
        f = DummyApp.describe_permission
        self.assertEqual(f('foo'), 'bar')
        self.assertEqual(f('post'), 'overridden')
        self.assertEqual(f('admin'), 'Set permissions.')
        self.assertEqual(f('does_not_exist'), '')


class TestInstall(WithDatabase):
    patches = [fake_app_patch]

    def test_that_it_creates_a_discussion(self):
        original_discussion_count = self.discussion_count()
        install_app()
        assert self.discussion_count() == original_discussion_count + 1

    def discussion_count(self):
        return model.Discussion.query.find().count()


class TestDefaultDiscussion(WithDatabase):
    patches = [fake_app_patch]

    def setup_method(self, method):
        super().setup_method(method)
        install_app()
        self.discussion = model.Discussion.query.get(
            shortname='my_mounted_app')

    def test_that_it_has_a_description(self):
        description = self.discussion.description
        assert description == 'Forum for my_mounted_app comments'

    def test_that_it_has_a_name(self):
        assert self.discussion.name == 'my_mounted_app Discussion'

    def test_that_its_shortname_is_taken_from_the_project(self):
        assert self.discussion.shortname == 'my_mounted_app'


class TestAppDefaults(WithDatabase):
    patches = [fake_app_patch]

    def setup_method(self, method):
        super().setup_method(method)
        self.app = install_app()

    def test_that_it_has_an_empty_sidebar_menu(self):
        assert self.app.sidebar_menu() == []

    def test_that_it_denies_access_for_everything(self):
        assert not self.app.has_access(model.User.anonymous(), 'any.topic')

    def test_default_sitemap(self):
        assert self.app.sitemap[0].label == 'My Mounted App'
        assert self.app.sitemap[0].url == '.'

    def test_not_exportable_by_default(self):
        assert not self.app.exportable

    def test_email_address(self):
        self.app.url = '/p/project/mount-point/'
        assert self.app.email_address == 'mount-point@project.p.in.localhost'


def install_app():
    project = create_project('myproject')
    app_config = create_app_config(project, 'my_mounted_app')
    # XXX: Remove project argument to install; it's redundant
    app = Application(project, app_config)
    app.install(project)
    return app
