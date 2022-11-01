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


from six.moves.urllib.parse import quote

from allura.tests import TestController
from allura.tests import decorators as td
from allura import model as M


class TestNewForgeController(TestController):

    @td.with_wiki
    def test_markdown_to_html(self):
        n = M.Neighborhood.query.get(name='Projects')
        r = self.app.get(
            '/nf/markdown_to_html?markdown=*aaa*bb[wiki:Home]&project=test&app=bugs&neighborhood=%s' % n._id, validate_chunk=True)
        assert '<p><em>aaa</em>bb<a class="alink" href="/p/test/wiki/Home/">[wiki:Home]</a></p>' in r, r

        # this happens to trigger an error
        bad_markdown = '<foo {bar}>'
        r = self.app.get('/nf/markdown_to_html?markdown=%s&project=test&app=bugs&neighborhood=%s' %
                         (quote(bad_markdown), n._id))
        r.mustcontain('The markdown supplied could not be parsed correctly.')
        r.mustcontain('<pre>&lt;foo {bar}&gt;</pre>')

    def test_markdown_syntax(self):
        r = self.app.get('/nf/markdown_syntax')
        r.mustcontain('Markdown Syntax')
        r.mustcontain('href="http://someurl"')

    def test_markdown_syntax_dialog(self):
        r = self.app.get('/nf/markdown_syntax_dialog')
        r.mustcontain('<h1>Markdown Syntax Guide</h1>')
        r.mustcontain('href="http://someurl"')
