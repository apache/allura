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
from datadiff.tools import assert_equal

from forgeimporters import google
from forgeimporters import base


class TestGoogleCodeProjectExtractor(TestCase):
    def setUp(self):
        self._p_urlopen = mock.patch.object(base.ProjectExtractor, 'urlopen')
        # self._p_soup = mock.patch.object(google, 'BeautifulSoup')
        self._p_soup = mock.patch.object(base, 'BeautifulSoup')
        self.urlopen = self._p_urlopen.start()
        self.soup = self._p_soup.start()
        self.project = mock.Mock(name='project')
        self.project.get_tool_data.return_value = 'my-project'

    def tearDown(self):
        for patcher in ('_p_urlopen', '_p_soup'):
            try:
                getattr(self, patcher).stop()
            except RuntimeError as e:
                if 'unstarted patcher' in str(e):
                    pass  # test case might stop them early
                else:
                    raise

    def test_init(self):
        extractor = google.GoogleCodeProjectExtractor('my-project', 'project_info')

        self.urlopen.assert_called_once_with('http://code.google.com/p/my-project/')
        self.soup.assert_called_once_with(self.urlopen.return_value)
        self.assertEqual(extractor.page, self.soup.return_value)

    def test_get_page(self):
        extractor = google.GoogleCodeProjectExtractor('my-project', 'project_info')
        self.assertEqual(1, self.urlopen.call_count)
        page = extractor.get_page('project_info')
        self.assertEqual(1, self.urlopen.call_count)
        self.assertEqual(page, extractor._page_cache['http://code.google.com/p/my-project/'])
        page = extractor.get_page('project_info')
        self.assertEqual(1, self.urlopen.call_count)
        self.assertEqual(page, extractor._page_cache['http://code.google.com/p/my-project/'])
        page = extractor.get_page('source_browse')
        self.assertEqual(2, self.urlopen.call_count)
        self.assertEqual(page, extractor._page_cache['http://code.google.com/p/my-project/source/browse/'])

    def test_get_page_url(self):
        extractor = google.GoogleCodeProjectExtractor('my-project')
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
        extractor.page.find.return_value.get.return_value = 'http://example.com/foo/bar/my-logo.png'
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
        self.assertEqual(gpe.get_issue_mod_date(), 'Thu Aug  8 14:56:23 2013')

    def test_get_issue_basic_fields(self):
        test_issue = open(pkg_resources.resource_filename('forgeimporters', 'tests/data/google/test-issue.html')).read()
        gpe = self._make_extractor(test_issue)
        self.assertEqual(gpe.get_issue_creator().name, 'john...@gmail.com')
        self.assertEqual(gpe.get_issue_creator().url, 'http://code.google.com/u/101557263855536553789/')
        self.assertEqual(gpe.get_issue_owner().name, 'john...@gmail.com')
        self.assertEqual(gpe.get_issue_owner().url, 'http://code.google.com/u/101557263855536553789/')
        self.assertEqual(gpe.get_issue_status(), 'Started')
        self._p_soup.stop()
        self.assertEqual(gpe.get_issue_summary(), 'Test "Issue"')
        assert_equal(gpe.get_issue_description(),
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
                '    if p.count &gt; 5:\n'
                '        print "Not &lt; 5 &amp; != 5"\n'
                '\n'
                'That\'s all'
            )
        self.assertEqual(gpe.get_issue_created_date(), 'Thu Aug  8 15:33:52 2013')
        self.assertEqual(gpe.get_issue_stars(), 1)

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

    def test_get_issue_attachments(self):
        test_issue = open(pkg_resources.resource_filename('forgeimporters', 'tests/data/google/test-issue.html')).read()
        gpe = self._make_extractor(test_issue)
        attachments = gpe.get_issue_attachments()
        self.assertEqual(len(attachments), 2)
        self.assertEqual(attachments[0].filename, 'at1.txt')
        self.assertEqual(attachments[0].url, 'http://allura-google-importer.googlecode.com/issues/attachment?aid=70000000&name=at1.txt&token=3REU1M3JUUMt0rJUg7ldcELt6LA%3A1376059941255')
        self.assertIsNone(attachments[0].type)
        self.assertEqual(attachments[1].filename, 'at2.txt')
        self.assertEqual(attachments[1].url, 'http://allura-google-importer.googlecode.com/issues/attachment?aid=70000001&name=at2.txt&token=C9Hn4s1-g38hlSggRGo65VZM1ys%3A1376059941255')
        self.assertIsNone(attachments[1].type)

    def test_iter_comments(self):
        test_issue = open(pkg_resources.resource_filename('forgeimporters', 'tests/data/google/test-issue.html')).read()
        gpe = self._make_extractor(test_issue)
        comments = list(gpe.iter_comments())
        self.assertEqual(len(comments), 4)
        expected = [
                {
                    'author.name': 'john...@gmail.com',
                    'author.url': 'http://code.google.com/u/101557263855536553789/',
                    'created_date': 'Thu Aug  8 15:35:15 2013',
                    'body': 'Test *comment* is a comment',
                    'updates': {'Status:': 'Started', 'Labels:': '-OpSys-Linux OpSys-Windows'},
                    'attachments': ['at2.txt'],
                },
                {
                    'author.name': 'john...@gmail.com',
                    'author.url': 'http://code.google.com/u/101557263855536553789/',
                    'created_date': 'Thu Aug  8 15:35:34 2013',
                    'body': 'Another comment',
                    'updates': {},
                    'attachments': [],
                },
                {
                    'author.name': 'john...@gmail.com',
                    'author.url': 'http://code.google.com/u/101557263855536553789/',
                    'created_date': 'Thu Aug  8 15:36:39 2013',
                    'body': 'Last comment',
                    'updates': {},
                    'attachments': ['at4.txt', 'at1.txt'],
                },
                {
                    'author.name': 'john...@gmail.com',
                    'author.url': 'http://code.google.com/u/101557263855536553789/',
                    'created_date': 'Thu Aug  8 15:36:57 2013',
                    'body': 'Oh, I forgot one',
                    'updates': {'Labels:': 'OpSys-OSX'},
                    'attachments': [],
                },
            ]
        for actual, expected in zip(comments, expected):
            self.assertEqual(actual.author.name, expected['author.name'])
            self.assertEqual(actual.author.url, expected['author.url'])
            self.assertEqual(actual.created_date, expected['created_date'])
            self.assertEqual(actual.body, expected['body'])
            self.assertEqual(actual.updates, expected['updates'])
            self.assertEqual([a.filename for a in actual.attachments], expected['attachments'])

class TestUserLink(TestCase):
    def test_plain(self):
        tag = mock.Mock()
        tag.string.strip.return_value = 'name'
        tag.get.return_value = None
        link = google.UserLink(tag)
        self.assertEqual(str(link), 'name')

    def test_linked(self):
        tag = mock.Mock()
        tag.string.strip.return_value = 'name'
        tag.get.return_value = '/p/project'
        link = google.UserLink(tag)
        self.assertEqual(str(link), '[name](http://code.google.com/p/project)')
