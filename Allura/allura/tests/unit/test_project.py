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
from mock import Mock

from tg import config

from allura import model as M
from allura.lib import helpers as h
from allura.app import SitemapEntry


class TestProject(unittest.TestCase):

    def test_grouped_navbar_entries(self):
        p = M.Project()
        sitemap_entries = [
            SitemapEntry('bugs', url='bugs url', tool_name='Tickets'),
            SitemapEntry('wiki', url='wiki url', tool_name='Wiki'),
            SitemapEntry('discuss', url='discuss url', tool_name='Discussion'),
            SitemapEntry('subproject', url='subproject url'),
            SitemapEntry('features', url='features url', tool_name='Tickets'),
            SitemapEntry('help', url='help url', tool_name='Discussion'),
            SitemapEntry('support reqs', url='support url',
                         tool_name='Tickets'),
        ]
        p.url = Mock(return_value='proj_url/')
        p.sitemap = Mock(return_value=sitemap_entries)
        entries = p.grouped_navbar_entries()
        expected = [
            ('Tickets \u25be', 'proj_url/_list/tickets', 3),
            ('wiki', 'wiki url', 0),
            ('Discussion \u25be', 'proj_url/_list/discussion', 2),
            ('subproject', 'subproject url', 0),
        ]
        expected_ticket_urls = ['bugs url', 'features url', 'support url']
        actual = [(e.label, e.url, len(e.matching_urls)) for e in entries]
        self.assertEqual(expected, actual)
        self.assertEqual(entries[0].matching_urls, expected_ticket_urls)

    def test_grouped_navbar_threshold(self):
        p = M.Project()
        sitemap_entries = [
            SitemapEntry('bugs', url='bugs url', tool_name='Tickets'),
            SitemapEntry('wiki', url='wiki url', tool_name='Wiki'),
            SitemapEntry('discuss', url='discuss url', tool_name='Discussion'),
            SitemapEntry('subproject', url='subproject url'),
            SitemapEntry('features', url='features url', tool_name='Tickets'),
            SitemapEntry('help', url='help url', tool_name='Discussion'),
            SitemapEntry('support reqs', url='support url',
                         tool_name='Tickets'),
        ]
        p.url = Mock(return_value='proj_url/')
        p.sitemap = Mock(return_value=sitemap_entries)
        p.tool_data['allura'] = {'grouping_threshold': 2}
        entries = p.grouped_navbar_entries()
        expected = [
            ('Tickets \u25be', 'proj_url/_list/tickets', 3),
            ('wiki', 'wiki url', 0),
            ('discuss', 'discuss url', 0),
            ('subproject', 'subproject url', 0),
            ('help', 'help url', 0),
        ]
        expected_ticket_urls = ['bugs url', 'features url', 'support url']
        actual = [(e.label, e.url, len(e.matching_urls)) for e in entries]
        self.assertEqual(expected, actual)
        self.assertEqual(entries[0].matching_urls, expected_ticket_urls)

    def test_social_account(self):
        p = M.Project()
        self.assertIsNone(p.social_account('Twitter'))

        p.set_social_account('Twitter', 'http://twitter.com/allura')
        self.assertEqual(p.social_account('Twitter')
                         .accounturl, 'http://twitter.com/allura')
        self.assertEqual(p.twitter_handle, 'http://twitter.com/allura')

    def test_should_update_index(self):
        p = M.Project()
        self.assertFalse(p.should_update_index({}, {}))
        old = {'last_updated': 1}
        new = {'last_updated': 2}
        self.assertFalse(p.should_update_index(old, new))
        old = {'last_updated': 1, 'a': 1}
        new = {'last_updated': 2, 'a': 1}
        self.assertFalse(p.should_update_index(old, new))
        old = {'last_updated': 1, 'a': 1}
        new = {'last_updated': 2, 'a': 2}
        self.assertTrue(p.should_update_index(old, new))

    def test_icon_url(self):
        p = M.Project(
            shortname='myproj',
            neighborhood = M.Neighborhood(url_prefix='/nbhd/'),
        )
        self.assertEqual(p.icon_url(), '/nbhd/myproj/icon')

        with h.push_config(config, **{'static.icon_base': 'https://mycdn.com/mysite'}):
            self.assertEqual(p.icon_url(), 'https://mycdn.com/mysite/nbhd/myproj/icon')
