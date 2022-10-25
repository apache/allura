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

from mock import patch
from tg import config

from allura.lib import helpers as h
from allura.tests import TestController


class TestTracImportController(TestController):

    def test_index(self):
        r = self.app.get('/p/import_project/trac/')
        assert 'Trac URL' in r

    def test_submit(self):
        r = self.app.get('/p/import_project/trac/')
        form = r.forms['project-import-form']
        form['trac_url'] = 'http://example.com/trac'
        form['project_name'] = 'My Project'
        form['project_shortname'] = 'my-project'
        form['user_map'] = ('', b'')

        with patch('forgeimporters.trac.requests.head') as mock_head:
            mock_head.return_value.status_code = 200  # so our 'trac_url' above is deemed as an okay URL
            r = form.submit()

        assert r.status_int == 302 and '/p/my-project' in r.location, \
            'Did not redirect as expected (status {} location {}).  Got a flash message: {} and inline errors: {}'.format(
                r.status_int,
                r.location,
                self.webflash(r),
                hasattr(r, 'html') and r.html.find_all('div', {'class': 'error'})
            )

    def test_import_with_phone_validation(self):
        self.app.extra_environ = {'username': 'test-user'}
        with h.push_config(config, **{'project.verify_phone': 'true'}):
            self.test_submit()
