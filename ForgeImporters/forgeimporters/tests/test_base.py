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
import errno

from formencode import Invalid
import mock
import pytest
from tg import expose, config
from webob.exc import HTTPUnauthorized

from alluratest.controller import TestController, setup_basic_test
from allura.tests import decorators as td
from allura.lib import helpers as h

from forgeimporters import base


class TestProjectExtractor(TestCase):

    @mock.patch('forgeimporters.base.h.urlopen')
    @mock.patch('six.moves.urllib.request.Request')
    def test_urlopen(self, Request, urlopen):
        r = base.ProjectExtractor.urlopen('myurl', data='foo')
        Request.assert_called_once_with('myurl', data='foo')
        req = Request.return_value
        req.add_header.assert_called_once_with(
            'User-Agent', 'Allura Data Importer (https://allura.apache.org/)')
        urlopen.assert_called_once_with(req, retries=3, codes=(408, 500, 502, 503, 504), timeout=120)
        self.assertEqual(r, urlopen.return_value)


@mock.patch.object(base, 'datetime')
@mock.patch.object(base, 'M')
@mock.patch.object(base, 'object_from_path')
@mock.patch.object(base, 'c')
@mock.patch.object(base, 'g')
def test_import_tool(g, c, object_from_path, M, _datetime):
    c.project = mock.Mock(name='project')
    c.user = mock.Mock(name='user')
    object_from_path.return_value = importer = mock.Mock()
    importer.return_value.source = 'source'
    importer.return_value.tool_label = 'label'
    base.import_tool(
        'forgeimporters.base.ToolImporter', project_name='project_name',
        mount_point='mount_point', mount_label='mount_label')
    app = importer.return_value.import_tool.return_value
    importer.return_value.import_tool.assert_called_once_with(
        c.project,
        c.user, project_name='project_name', mount_point='mount_point',
        mount_label='mount_label')
    M.Project.query.update.assert_called_once_with(
        {'_id': c.project._id},
        {'$set': {'last_updated': _datetime.utcnow()}})
    g.director.create_activity.assert_called_once_with(
        c.user, "imported",
        app.config, related_nodes=[c.project], tags=['import'])
    g.post_event.assert_called_once_with(
        'import_tool_task_succeeded',
        'source',
        'label',
    )


@mock.patch.object(base.traceback, 'format_exc')
@mock.patch.object(base, 'ToolImporter')
@mock.patch.object(base, 'g')
def test_import_tool_failed(g, ToolImporter, format_exc):
    setup_basic_test()
    format_exc.return_value = 'my traceback'

    importer = mock.Mock(source='importer_source',
                         tool_label='importer_tool_label')
    importer.import_tool.side_effect = RuntimeError('my error')
    ToolImporter.return_value = importer

    with pytest.raises(RuntimeError):
        base.import_tool('forgeimporters.base.ToolImporter', project_name='project_name')
    g.post_event.assert_called_once_with(
        'import_tool_task_failed',
        error=str(importer.import_tool.side_effect),
        traceback='my traceback',
        importer_source='importer_source',
        importer_tool_label='importer_tool_label',
        project_name='project_name',
    )


def ep(name, source=None, importer=None, **kw):
    mep = mock.Mock(name='mock_ep', **kw)
    mep.name = name
    if importer is not None:
        mep.load.return_value = importer
    else:
        mep.load.return_value.source = source
        mep.lv = mep.load.return_value.return_value
        mep.lv.source = source
    return mep


class TestProjectImporter(TestCase):

    @mock.patch.object(base.h, 'iter_entry_points')
    def test_tool_importers(self, iep):
        eps = iep.return_value = [
            ep('ep1', 'foo'), ep('ep2', 'bar'), ep('ep3', 'foo')]
        pi = base.ProjectImporter(mock.Mock(name='neighborhood'))
        pi.source = 'foo'
        self.assertEqual(pi.tool_importers,
                         {'ep1': eps[0].lv, 'ep3': eps[2].lv})
        iep.assert_called_once_with('allura.importers')

    @mock.patch.object(base.ToolImporter, 'by_name')
    @mock.patch.object(base, 'redirect')
    @mock.patch.object(base, 'flash')
    @mock.patch.object(base, 'import_tool')
    @mock.patch.object(base, 'M')
    @mock.patch.object(base, 'c')
    def test_process(self, c, M, import_tool, flash, redirect, by_name):
        base.ToolImporter.target_app_ep_names = []
        by_name.return_value = base.ToolImporter()

        pi = base.ProjectImporter(mock.Mock())
        pi.source = 'Source'
        pi.after_project_create = mock.Mock()
        pi.neighborhood.register_project.return_value.script_name = 'script_name/'
        kw = {
            'project_name': 'project_name',
            'project_shortname': 'shortname',
            'tools': ['tool'],
        }
        with mock.patch.dict(base.config, {'site_name': 'foo'}):
            pi.process(**kw)
        pi.neighborhood.register_project.assert_called_once_with(
            'shortname', project_name='project_name')
        pi.after_project_create.assert_called_once_with(c.project, **kw)
        import_tool.post.assert_called_once_with(
            'forgeimporters.base.ToolImporter', **kw)
        M.AuditLog.log.assert_called_once_with('import project from Source')
        self.assertEqual(flash.call_count, 1)
        redirect.assert_called_once_with('script_name/admin/overview')

    @mock.patch.object(base.h, 'request')
    @mock.patch.object(base, 'require_access')
    @mock.patch.object(base.h, 'c')
    def test_login_overlay(self, c, require_access, request):
        pi = base.ProjectImporter(mock.Mock())
        require_access.side_effect = HTTPUnauthorized

        c.show_login_overlay = False
        request.path = '/test-importer/'
        pi._check_security()
        self.assertEqual(c.show_login_overlay, True)

        c.show_login_overlay = False
        request.path = '/test-importer/check_names/'
        pi._check_security()
        self.assertEqual(c.show_login_overlay, True)

        c.show_login_overlay = False
        request.path = '/test-importer/process/'
        with td.raises(HTTPUnauthorized):
            pi._check_security()
        self.assertEqual(c.show_login_overlay, False)


TA1 = mock.Mock(tool_label='foo', tool_description='foo_desc')
TA2 = mock.Mock(tool_label='qux', tool_description='qux_desc')
TA3 = mock.Mock(tool_label='baz', tool_description='baz_desc')


class TI1Controller(base.ToolImportController):
    @expose()
    def index(self, *a, **kw):
        return 'test importer 1 controller webpage'


class TI1(base.ToolImporter):
    target_app = TA1
    controller = TI1Controller


class TI2(base.ToolImporter):
    target_app = TA2
    tool_label = 'bar'
    tool_description = 'bar_desc'


class TI3(base.ToolImporter):
    target_app = [TA2, TA2]


class TestToolImporter(TestCase):

    @mock.patch.object(base.h, 'iter_entry_points')
    def test_by_name(self, iep):
        eps = iep.return_value = [ep('my-name', 'my-source')]
        importer = base.ToolImporter.by_name('my-name')
        iep.assert_called_once_with('allura.importers', 'my-name')
        self.assertEqual(importer, eps[0].lv)

        iep.reset_mock()
        iep.return_value = []
        importer = base.ToolImporter.by_name('other-name')
        iep.assert_called_once_with('allura.importers', 'other-name')
        self.assertEqual(importer, None)

    @mock.patch.object(base.h, 'iter_entry_points')
    def test_by_app(self, iep):
        eps = iep.return_value = [
            ep('importer1', importer=TI1),
            ep('importer2', importer=TI2),
            ep('importer3', importer=TI3),
        ]
        importers = base.ToolImporter.by_app(TA2)
        self.assertEqual(set(importers.keys()), {
            'importer2',
            'importer3',
        })
        self.assertIsInstance(importers['importer2'], TI2)
        self.assertIsInstance(importers['importer3'], TI3)

    def test_tool_label(self):
        self.assertEqual(TI1().tool_label, 'foo')
        self.assertEqual(TI2().tool_label, 'bar')
        self.assertEqual(TI3().tool_label, 'qux')

    def test_tool_description(self):
        self.assertEqual(TI1().tool_description, 'foo_desc')
        self.assertEqual(TI2().tool_description, 'bar_desc')
        self.assertEqual(TI3().tool_description, 'qux_desc')


class TestToolsValidator(TestCase):

    def setup_method(self, method):
        self.tv = base.ToolsValidator('good-source')

    @mock.patch.object(base.ToolImporter, 'by_name')
    def test_empty(self, by_name):
        self.assertEqual(self.tv.to_python(''), [])
        self.assertEqual(by_name.call_count, 0)

    @mock.patch.object(base.ToolImporter, 'by_name')
    def test_no_ep(self, by_name):
        eps = by_name.return_value = None
        with self.assertRaises(Invalid) as cm:
            self.tv.to_python('my-value')
        self.assertEqual(cm.exception.msg, 'Invalid tool selected: my-value')
        by_name.assert_called_once_with('my-value')

    @mock.patch.object(base.ToolImporter, 'by_name')
    def test_bad_source(self, by_name):
        eps = by_name.return_value = ep('ep1', 'bad-source').lv
        with self.assertRaises(Invalid) as cm:
            self.tv.to_python('my-value')
        self.assertEqual(cm.exception.msg, 'Invalid tool selected: my-value')
        by_name.assert_called_once_with('my-value')

    @mock.patch.object(base.ToolImporter, 'by_name')
    def test_multiple(self, by_name):
        eps = by_name.side_effect = [
            ep('ep1', 'bad-source').lv, ep('ep2', 'good-source').lv, ep('ep3', 'bad-source').lv]
        with self.assertRaises(Invalid) as cm:
            self.tv.to_python(['value1', 'value2', 'value3'])
        self.assertEqual(cm.exception.msg,
                         'Invalid tools selected: value1, value3')
        self.assertEqual(by_name.call_args_list, [
            mock.call('value1'),
            mock.call('value2'),
            mock.call('value3'),
        ])

    @mock.patch.object(base.ToolImporter, 'by_name')
    def test_valid(self, by_name):
        eps = by_name.side_effect = [
            ep('ep1', 'good-source').lv, ep('ep2', 'good-source').lv, ep('ep3', 'bad-source').lv]
        self.assertEqual(
            self.tv.to_python(['value1', 'value2']), ['value1', 'value2'])
        self.assertEqual(by_name.call_args_list, [
            mock.call('value1'),
            mock.call('value2'),
        ])


class TestProjectToolsImportController(TestController):

    def test_pages(self):
        admin_page = self.app.get('/admin/')
        with mock.patch.object(base.h, 'iter_entry_points') as iep:
            iep.return_value = [
                ep('importer1', importer=TI1),
                ep('importer2', importer=TI2),
                ep('importer3', importer=TI3),
            ]
            import_main_page = admin_page.click('Import')
        url = import_main_page.request.path
        assert url.endswith('/admin/ext/import/'), url

        with mock.patch.object(base.ToolImporter, 'by_name') as by_name:
            by_name.return_value = TI1
            import1_page = import_main_page.click('Import', href=r'importer1$')
        url = import1_page.request.path
        assert url.endswith('/admin/ext/import/importer1'), url
        assert import1_page.text == 'test importer 1 controller webpage'

    @mock.patch.object(base.h, 'iter_entry_points')
    def test_hidden(self, iep):
        iep.return_value = [
            ep('importer1', importer=TI1),
            ep('importer2', importer=TI2),
        ]
        admin_page = self.app.get('/admin/')
        with h.push_config(config, hidden_importers='importer1'):
            import_main_page = admin_page.click('Import')
        url = import_main_page.request.path
        assert url.endswith('/admin/ext/import/'), url
        assert not import_main_page.html.find('a', href='importer1')
        assert import_main_page.html.find('a', href='importer2')


def test_get_importer_upload_path():
    project = mock.Mock(
        shortname='prefix/shortname',
        is_nbhd_project=False,
        is_user_project=False,
        is_root=False,
        url=lambda: 'n_url/',
        neighborhood=mock.Mock(url_prefix='p/'),
    )
    with h.push_config(config, importer_upload_path='path/{nbhd}/{project}'):
        assert base.get_importer_upload_path(project) == 'path/p/prefix'
        project.is_nbhd_project = True
        assert base.get_importer_upload_path(project) == 'path/p/n_url'
        project.is_nbhd_project = False
        project.is_user_project = True
        assert (base.get_importer_upload_path(project) ==
                     'path/p/shortname')
        project.is_user_project = False
        project.is_root = True
        assert (base.get_importer_upload_path(project) ==
                     'path/p/prefix/shortname')


@mock.patch.object(base, 'os')
@mock.patch.object(base, 'get_importer_upload_path')
def test_save_importer_upload(giup, os):
    os.path.join = lambda *a: '/'.join(a)
    giup.return_value = 'path'
    os.makedirs.side_effect = OSError(errno.EEXIST, 'foo')
    with mock.patch('forgeimporters.base.open') as m_open:
        m_open = mock.mock_open(m_open)
        fp = m_open.return_value.__enter__.return_value
        base.save_importer_upload('project', 'file', 'data')
        os.makedirs.assert_called_once_with('path')
        m_open.assert_called_once_with('path/file', 'w', encoding='utf-8')
        fp.write.assert_called_once_with('data')

    os.makedirs.side_effect = OSError(errno.EACCES, 'foo')
    with pytest.raises(OSError):
        base.save_importer_upload('project', 'file', 'data')


class TestFile:

    @mock.patch.object(base, 'ProjectExtractor')
    def test_type(self, PE):
        PE().page = {
            'content-type': 'image/png',
            'data': 'data',
        }
        f = base.File('http://example.com/barbaz.jpg')
        assert f.type == 'image/jpeg'

        f = base.File('http://example.com/barbaz')
        assert f.type == 'image/png'
