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
import logging
from urllib.parse import quote

from ming.odm import ThreadLocalODMSession
from testfixtures import LogCapture

from allura.tests import TestController
from allura.tests import decorators as td
from allura import model as M


class TestNewForgeController(TestController):

    @td.with_wiki
    def test_markdown_to_html(self):
        n = M.Neighborhood.query.get(name='Projects')
        r = self.app.get(
            '/nf/markdown_to_html?markdown=*aaa*bb[wiki:Home]&project=test&app=wiki&neighborhood=%s' % n._id, validate_chunk=True)
        assert '<p><em>aaa</em>bb<a class="alink" href="/p/test/wiki/Home/">[wiki:Home]</a></p>' in r, r

        # this used to trigger a parsing error; now the unknown tag is escaped
        bad_markdown = '<foo {bar}>'
        r = self.app.get('/nf/markdown_to_html?markdown=%s&project=test&app=wiki&neighborhood=%s' %
                         (quote(bad_markdown), n._id))
        r.mustcontain('&lt;foo {bar}=""&gt;&lt;/foo&gt;')

        r = self.app.get('/nf/markdown_to_html?markdown=*aaa*bb[wiki:Home]&project=test&app=wiki&neighborhood=bogus',
                         status=400)

    @td.with_wiki
    def test_markdown_to_html_private_project(self):
        # Make the test project private by removing anonymous read access
        p = M.Project.query.get(shortname='test')
        p.acl = [ace for ace in p.acl
                 if not (ace.access == M.ACE.ALLOW
                         and ace.permission == 'read'
                         and ace.role_id == M.ProjectRole.anonymous(p)._id)]
        ThreadLocalODMSession.flush_all()

        n = M.Neighborhood.query.get(name='Projects')
        # Authenticated user with access should still work
        r = self.app.get(
            '/nf/markdown_to_html?markdown=*hello*&project=test&app=wiki&neighborhood=%s' % n._id,
            extra_environ=dict(username='test-admin'))
        assert '<p><em>hello</em></p>' in r, r

        # test-user and *anonymous get different errors, but that's ok, neither work:
        self.app.get(
            '/nf/markdown_to_html?markdown=*hello*&project=test&app=wiki&neighborhood=%s' % n._id,
            extra_environ=dict(username='test-user'),
            status=403)
        self.app.get(
            '/nf/markdown_to_html?markdown=*hello*&project=test&app=wiki&neighborhood=%s' % n._id,
            extra_environ=dict(username='*anonymous'),
            status=302)

    def test_markdown_syntax(self):
        with LogCapture(level=logging.INFO) as logs:
            r = self.app.get('/nf/markdown_syntax')
        r.mustcontain('Markdown Syntax')
        r.mustcontain('href="http://someurl"')
        r.mustcontain(no='ERROR')

        markdown_invalid_classes = [log[2] for log in logs if 'invalid class' in log[2]]
        assert not markdown_invalid_classes

    def test_markdown_syntax_dialog(self):
        r = self.app.get('/nf/markdown_syntax_dialog')
        r.mustcontain('<h1>Markdown Syntax Guide</h1>')
        r.mustcontain('href="http://someurl"')
        r.mustcontain(no='ERROR')
