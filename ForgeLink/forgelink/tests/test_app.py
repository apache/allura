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

import tempfile
import json

from tg import tmpl_context as c

from allura.tests import decorators as td
from allura import model as M
from alluratest.controller import setup_basic_test


class TestBulkExport:

    def setup_method(self, method):
        setup_basic_test()

    @td.with_link
    def test_bulk_export(self):
        # Clear out some context vars, to properly simulate how this is run from the export task
        # Besides, it's better not to need c context vars
        c.app = c.project = None

        project = M.Project.query.get(shortname='test')
        link = project.app_instance('link')
        link.config.options['url'] = 'http://domain.net'
        f = tempfile.TemporaryFile('w+')
        link.bulk_export(f)
        f.seek(0)
        assert json.loads(f.read())['url'] == 'http://domain.net'
