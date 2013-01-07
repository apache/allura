import unittest
from mock import Mock

from allura import model as M
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
            SitemapEntry('support reqs', url='support url', tool_name='Tickets'),
        ]
        p.url = Mock(return_value='proj_url/')
        p.sitemap = Mock(return_value=sitemap_entries)
        expected = [
            ('Tickets', 'proj_url/_list/tickets', 3),
            ('wiki', 'wiki url', 0),
            ('Discussion', 'proj_url/_list/discussion', 2),
            ('subproject', 'subproject url', 0),
        ]
        actual = [(e.label, e.url, len(e.matching_urls))
                for e in p.grouped_navbar_entries()]
        self.assertEqual(expected, actual)

    def test_grouped_navbar_threshold(self):
        p = M.Project()
        sitemap_entries = [
            SitemapEntry('bugs', url='bugs url', tool_name='Tickets'),
            SitemapEntry('wiki', url='wiki url', tool_name='Wiki'),
            SitemapEntry('discuss', url='discuss url', tool_name='Discussion'),
            SitemapEntry('subproject', url='subproject url'),
            SitemapEntry('features', url='features url', tool_name='Tickets'),
            SitemapEntry('help', url='help url', tool_name='Discussion'),
            SitemapEntry('support reqs', url='support url', tool_name='Tickets'),
        ]
        p.url = Mock(return_value='proj_url/')
        p.sitemap = Mock(return_value=sitemap_entries)
        p.tool_data['allura'] = {'grouping_threshold': 2}
        expected = [
            ('Tickets', 'proj_url/_list/tickets', 3),
            ('wiki', 'wiki url', 0),
            ('discuss', 'discuss url', 0),
            ('subproject', 'subproject url', 0),
            ('help', 'help url', 0),
        ]
        actual = [(e.label, e.url, len(e.matching_urls))
                for e in p.grouped_navbar_entries()]
        self.assertEqual(expected, actual)
