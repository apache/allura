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
import pkg_resources

import mock

from forgeimporters import google
from forgeimporters import base


class TestGoogleCodeProjectExtractor(TestCase):
    def setUp(self):
        self._p_urlopen = mock.patch.object(base.ProjectExtractor, 'urlopen')
        self._p_soup = mock.patch.object(google, 'BeautifulSoup')
        self.urlopen = self._p_urlopen.start()
        self.soup = self._p_soup.start()
        self.project = mock.Mock(name='project')
        self.project.get_tool_data.return_value = 'my-project'

    def tearDown(self):
        self._p_urlopen.stop()
        self._p_soup.stop()

    def test_init(self):
        extractor = google.GoogleCodeProjectExtractor('my-project', 'project_info')

        self.urlopen.assert_called_once_with('http://code.google.com/p/my-project/')
        self.soup.assert_called_once_with(self.urlopen.return_value)
        self.assertEqual(extractor.page, self.soup.return_value)

    def test_get_page(self):
        extractor = google.GoogleCodeProjectExtractor(self.project, 'my-project', 'project_info')
        self.assertEqual(1, self.urlopen.call_count)
        page = extractor.get_page('project_info')
        self.assertEqual(1, self.urlopen.call_count)
        self.assertEqual(page, extractor._page_cache['project_info'])

    def test_get_page_url(self):
        extractor = google.GoogleCodeProjectExtractor(self.project, 'my-project')
        self.assertEqual(extractor.get_page_url('project_info'),
                'http://code.google.com/p/my-project/')

    def test_get_short_description(self):
        extractor = google.GoogleCodeProjectExtractor('my-project', 'project_info')
        extractor.page.find.return_value.string = 'My Super Project'

        extractor.get_short_description(self.project)

        extractor.page.find.assert_called_once_with(itemprop='description')
        self.assertEqual(self.project.short_description, 'My Super Project')

    @mock.patch.object(google, 'StringIO')
    @mock.patch.object(google, 'M')
    def test_get_icon(self, M, StringIO):
        self.urlopen.return_value.info.return_value = {'content-type': 'image/png'}
        extractor = google.GoogleCodeProjectExtractor('my-project', 'project_info')
        extractor.page.find.return_value.attrMap = {'src': 'http://example.com/foo/bar/my-logo.png'}
        self.urlopen.reset_mock()

        extractor.get_icon(self.project)

        extractor.page.find.assert_called_once_with(itemprop='image')
        self.urlopen.assert_called_once_with('http://example.com/foo/bar/my-logo.png')
        self.urlopen.return_value.info.assert_called_once_with()
        StringIO.assert_called_once_with(self.urlopen.return_value.read.return_value)
        M.ProjectFile.save_image.assert_called_once_with(
            'my-logo.png', StringIO.return_value, 'image/png', square=True,
            thumbnail_size=(48,48), thumbnail_meta={
                'project_id': self.project._id, 'category': 'icon'})

    @mock.patch.object(google, 'M')
    def test_get_license(self, M):
        self.project.trove_license = []
        extractor = google.GoogleCodeProjectExtractor('my-project', 'project_info')
        extractor.page.find.return_value.findNext.return_value.find.return_value.string = '  New BSD License  '
        trove = M.TroveCategory.query.get.return_value

        extractor.get_license(self.project)

        extractor.page.find.assert_called_once_with(text='Code license')
        extractor.page.find.return_value.findNext.assert_called_once_with()
        extractor.page.find.return_value.findNext.return_value.find.assert_called_once_with('a')
        self.assertEqual(self.project.trove_license, [trove._id])
        M.TroveCategory.query.get.assert_called_once_with(fullname='BSD License')

        M.TroveCategory.query.get.reset_mock()
        extractor.page.find.return_value.findNext.return_value.find.return_value.string = 'non-existant license'
        extractor.get_license(self.project)
        M.TroveCategory.query.get.assert_called_once_with(fullname='Other/Proprietary License')

    def _make_extractor(self, html):
        from BeautifulSoup import BeautifulSoup
        with mock.patch.object(base.ProjectExtractor, 'urlopen'):
            extractor = google.GoogleCodeProjectExtractor('my-project')
        extractor.page = BeautifulSoup(html)
        extractor.get_page = lambda pagename: extractor.page
        extractor.url="http://test/source/browse"
        return extractor

    def test_get_repo_type_happy_path(self):
        extractor = self._make_extractor(
                '<span id="crumb_root">\nsvn/&nbsp;</span>')
        self.assertEqual('svn', extractor.get_repo_type())

    def test_get_repo_type_no_crumb_root(self):
        extractor = self._make_extractor('')
        with self.assertRaises(Exception) as cm:
            extractor.get_repo_type()
        self.assertEqual(str(cm.exception),
                "Couldn't detect repo type: no #crumb_root in "
                "http://test/source/browse")

    def test_get_repo_type_unknown_repo_type(self):
        extractor = self._make_extractor(
                '<span id="crumb_root">cvs</span>')
        with self.assertRaises(Exception) as cm:
            extractor.get_repo_type()
        self.assertEqual(str(cm.exception), "Unknown repo type: cvs")

    def test_empty_issue(self):
        empty_issue = open(pkg_resources.resource_filename('forgeimporters', 'tests/data/google/empty-issue.html')).read()
        gpe = self._make_extractor(empty_issue)
        self.assertIsNone(gpe.get_issue_owner())
        self.assertEqual(gpe.get_issue_status(), '')
        self.assertEqual(gpe.get_issue_attachments(), [])
        self.assertEqual(list(gpe.iter_comments()), [])

    def test_get_issue_basic_fields(self):
        test_issue = open(pkg_resources.resource_filename('forgeimporters', 'tests/data/google/test-issue.html')).read()
        gpe = self._make_extractor(test_issue)
        self.assertEqual(gpe.get_issue_creator().name, 'john...@gmail.com')
        self.assertEqual(gpe.get_issue_creator().link, 'http://code.google.com/u/101557263855536553789/')
        self.assertEqual(gpe.get_issue_owner().name, 'john...@gmail.com')
        self.assertEqual(gpe.get_issue_owner().link, 'http://code.google.com/u/101557263855536553789/')
        self.assertEqual(gpe.get_issue_status(), 'Started')
        self.assertEqual(gpe.get_issue_summary(), 'Test Issue')
        self.assertEqual(gpe.get_issue_description(),
                'Test *Issue* for testing\n'
                '\n'
                '  1. Test List\n'
                '  2. Item\n'
                '\n'
                '**Testing**\n'
                '\n'
                ' * Test list 2\n'
                ' * Item\n'
                '\n'
                '# Test Section\n'
                '\n'
                '    p = source.test_issue.post()\n'
                '    p.count = p.count *5 #* 6\n'
                '\n'
                'That\'s all'
            )
        self.assertEqual(gpe.get_issue_created_date(), 'Thu Aug  8 15:33:52 2013')

    def test_get_issue_mod_date(self):
        test_issue = open(pkg_resources.resource_filename('forgeimporters', 'tests/data/google/test-issue.html')).read()
        gpe = self._make_extractor(test_issue)
        self.assertEqual(gpe.get_issue_mod_date(), 'Thu Aug  8 15:36:57 2013')

    def test_get_issue_labels(self):
        test_issue = open(pkg_resources.resource_filename('forgeimporters', 'tests/data/google/test-issue.html')).read()
        gpe = self._make_extractor(test_issue)
        self.assertEqual(gpe.get_issue_labels(), [
                'Type-Defect',
                'Priority-Medium',
                'Milestone-Release1.0',
                'OpSys-All',
                'Component-Logic',
                'Performance',
                'Security',
                'OpSys-Windows',
                'OpSys-OSX',
            ])
