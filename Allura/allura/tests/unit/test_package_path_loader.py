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


from collections import OrderedDict
from unittest import TestCase

import jinja2
import mock
import pytest
from tg import config

from allura.lib.package_path_loader import PackagePathLoader


class TestPackagePathLoader(TestCase):

    @mock.patch('pkg_resources.resource_filename')
    @mock.patch('pkg_resources.iter_entry_points')
    def test_load_paths(self, iter_entry_points, resource_filename):
        eps = iter_entry_points.return_value.__iter__.return_value = [
            mock.Mock(ep_name='ep0', module_name='eps.ep0'),
            mock.Mock(ep_name='ep1', module_name='eps.ep1'),
            mock.Mock(ep_name='ep2', module_name='eps.ep2'),
        ]
        for ep in eps:
            ep.name = ep.ep_name
        resource_filename.side_effect = lambda m, r: 'path:' + m

        paths = PackagePathLoader()._load_paths()

        assert paths == [
            ['site-theme', None],
            ['ep0', 'path:eps.ep0'],
            ['ep1', 'path:eps.ep1'],
            ['ep2', 'path:eps.ep2'],
            ['allura', '/'],
        ]
        assert type(paths[0]) == list
        assert resource_filename.call_args_list == [
            mock.call('eps.ep0', ''),
            mock.call('eps.ep1', ''),
            mock.call('eps.ep2', ''),
        ]

    @mock.patch('pkg_resources.iter_entry_points')
    def test_load_rules(self, iter_entry_points):
        eps = iter_entry_points.return_value.__iter__.return_value = [
            mock.Mock(ep_name='ep0', rules=[('>', 'allura')]),
            mock.Mock(ep_name='ep1', rules=[('=', 'allura')]),
            mock.Mock(ep_name='ep2', rules=[('<', 'allura')]),
        ]
        for ep in eps:
            ep.name = ep.ep_name
            ep.load.return_value.template_path_rules = ep.rules

        order_rules, replacement_rules = PackagePathLoader()._load_rules()

        assert order_rules == [('ep0', 'allura'), ('allura', 'ep2')]
        assert replacement_rules == {'allura': 'ep1'}

        eps = iter_entry_points.return_value.__iter__.return_value = [
            mock.Mock(ep_name='ep0', rules=[('?', 'allura')]),
        ]
        for ep in eps:
            ep.name = ep.ep_name
            ep.load.return_value.template_path_rules = ep.rules
        pytest.raises(jinja2.TemplateError, PackagePathLoader()._load_rules)

    def test_replace_signposts(self):
        ppl = PackagePathLoader()
        ppl._replace_signpost = mock.Mock()
        paths = [
                ['site-theme', None],
            ['ep0', '/ep0'],
            ['ep1', '/ep1'],
            ['ep2', '/ep2'],
            ['allura', '/'],
        ]
        rules = OrderedDict([
            ('allura', 'ep2'),
            ('site-theme', 'ep1'),
            ('foo', 'ep1'),
            ('ep0', 'bar'),
        ])

        ppl._replace_signposts(paths, rules)

        assert paths == [
            ['site-theme', '/ep1'],
            ['ep0', '/ep0'],
            ['allura', '/ep2'],
        ]

    def test_sort_paths(self):
        paths = [
                ['site-theme', None],
            ['ep0', '/ep0'],
            ['ep1', '/ep1'],
            ['ep2', '/ep2'],
            ['ep3', '/ep3'],
            ['allura', '/'],
        ]
        rules = [
            ('allura', 'ep0'),
            ('ep3', 'ep1'),
            ('ep2', 'ep1'),
            ('ep4', 'ep1'),  # rules referencing missing paths
            ('ep2', 'ep5'),
        ]

        PackagePathLoader()._sort_paths(paths, rules)

        assert paths == [
            ['site-theme', None],
            ['ep2', '/ep2'],
            ['ep3', '/ep3'],
            ['ep1', '/ep1'],
            ['allura', '/'],
            ['ep0', '/ep0'],
        ]

    def test_init_paths(self):
        paths = [
            ['root', '/'],
            ['none', None],
            ['tail', '/tail'],
        ]
        ppl = PackagePathLoader()
        ppl._load_paths = mock.Mock(return_value=paths)
        ppl._load_rules = mock.Mock(return_value=('order_rules', 'repl_rules'))
        ppl._replace_signposts = mock.Mock()
        ppl._sort_paths = mock.Mock()

        output = ppl.init_paths()

        ppl._load_paths.assert_called_once_with()
        ppl._load_rules.assert_called_once_with()
        ppl._sort_paths.assert_called_once_with(paths, 'order_rules')
        ppl._replace_signposts.assert_called_once_with(paths, 'repl_rules')

        assert output == ['/', '/tail']

    @mock.patch('jinja2.FileSystemLoader')
    def test_fs_loader(self, FileSystemLoader):
        ppl = PackagePathLoader()
        ppl.init_paths = mock.Mock(return_value=['path1', 'path2'])
        FileSystemLoader.return_value = 'fs_loader'

        output1 = ppl.fs_loader
        output2 = ppl.fs_loader

        ppl.init_paths.assert_called_once_with()
        FileSystemLoader.assert_called_once_with(['path1', 'path2'])
        assert output1 == 'fs_loader'
        assert output1 is output2

    @mock.patch.dict(config, {'disable_template_overrides': False})
    @mock.patch('jinja2.FileSystemLoader')
    def test_get_source(self, fs_loader):
        ppl = PackagePathLoader()
        ppl.init_paths = mock.Mock()
        fs_loader().get_source.return_value = 'fs_load'

        # override exists
        output = ppl.get_source('env', 'allura.ext.admin:templates/audit.html')

        assert output == 'fs_load'
        fs_loader().get_source.assert_called_once_with(
            'env', 'override/allura/ext/admin/templates/audit.html')

        fs_loader().get_source.reset_mock()
        fs_loader().get_source.side_effect = [
            jinja2.TemplateNotFound('test'), 'fs_load']

        with mock.patch('pkg_resources.resource_filename') as rf:
            rf.return_value = 'resource'
            # no override, ':' in template
            output = ppl.get_source(
                'env', 'allura.ext.admin:templates/audit.html')
            rf.assert_called_once_with(
                'allura.ext.admin', 'templates/audit.html')

        assert output == 'fs_load'
        assert fs_loader().get_source.call_count == 2
        fs_loader().get_source.assert_called_with('env', 'resource')

        fs_loader().get_source.reset_mock()
        fs_loader().get_source.side_effect = [
            jinja2.TemplateNotFound('test'), 'fs_load']

        # no override, ':' not in template
        output = ppl.get_source('env', 'templates/audit.html')

        assert output == 'fs_load'
        assert fs_loader().get_source.call_count == 2
        fs_loader().get_source.assert_called_with(
            'env', 'templates/audit.html')

    @mock.patch('jinja2.FileSystemLoader')
    def test_override_disable(self, fs_loader):
        ppl = PackagePathLoader()
        ppl.init_paths = mock.Mock()
        fs_loader().get_source.side_effect = jinja2.TemplateNotFound('test')

        pytest.raises(
            jinja2.TemplateError,
            ppl.get_source, 'env', 'allura.ext.admin:templates/audit.html')
        assert fs_loader().get_source.call_count == 1
        fs_loader().get_source.reset_mock()

        with mock.patch.dict(config, {'disable_template_overrides': False}):
            pytest.raises(
                jinja2.TemplateError,
                ppl.get_source, 'env', 'allura.ext.admin:templates/audit.html')
            assert fs_loader().get_source.call_count == 2
