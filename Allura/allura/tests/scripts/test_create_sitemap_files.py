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

import os
from shutil import rmtree
import xml.etree.ElementTree as ET

from tg import tmpl_context as c
from testfixtures import TempDirectory

from alluratest.controller import setup_basic_test
from allura import model as M
from allura.lib import helpers as h
from allura.scripts.create_sitemap_files import CreateSitemapFiles


class TestCreateSitemapFiles:

    def setup_method(self, method):
        setup_basic_test()

    def run_script(self, options):
        cls = CreateSitemapFiles
        opts = cls.parser().parse_args(options)
        with h.push_config(c, user=M.User.anonymous()):  # tasks & scripts have c.user set
            cls.execute(opts)

    def test_create(self):
        with TempDirectory() as tmpdir:
            rmtree(tmpdir.path)  # needs to be non-existent for the script
            self.run_script(['-o', tmpdir.path])

            tmpdir.compare(['sitemap-0.xml', 'sitemap.xml'],recursive=False, files_only=True)

            xml_index = ET.parse(os.path.join(tmpdir.path, 'sitemap.xml'))
            ns = {'ns0': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            locs = [loc.text for loc in xml_index.findall('ns0:sitemap/ns0:loc', ns)]
            assert 'http://localhost/allura_sitemap/sitemap-0.xml' in locs

            xml_0 = ET.parse(os.path.join(tmpdir.path, 'sitemap-0.xml'))
            urls = [loc.text for loc in xml_0.findall('ns0:url/ns0:loc', ns)]
            assert 'http://localhost/p/wiki/' not in urls  # blank wiki pages omitted from sitemap
            assert 'http://localhost/p/test/sub1/' in urls
