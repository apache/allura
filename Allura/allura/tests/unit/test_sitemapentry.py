import unittest
from mock import Mock

from allura.app import SitemapEntry


class TestSitemapEntry(unittest.TestCase):
    def test_matches_url(self):
        request = Mock(upath_info='/p/project/tool/artifact')
        s1 = SitemapEntry('tool', url='/p/project/tool')
        s2 = SitemapEntry('tool2', url='/p/project/tool2')
        s3 = SitemapEntry('Tool', url='/p/project/_list/tool')
        s3.matching_urls.append('/p/project/tool')
        self.assertTrue(s1.matches_url(request))
        self.assertFalse(s2.matches_url(request))
        self.assertTrue(s3.matches_url(request))
