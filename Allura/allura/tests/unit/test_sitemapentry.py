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
