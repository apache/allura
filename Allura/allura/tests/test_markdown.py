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
import mock

from allura.lib import markdown_extensions as mde


class TestTracRef1(unittest.TestCase):

    @mock.patch('allura.lib.markdown_extensions.M.Shortlink.lookup')
    def test_no_such_artifact(self, lookup):
        lookup.return_value = None
        self.assertEqual(mde.TracRef1().sub('#100'), '#100')

    def test_skip_if_brackets(self):
        self.assertEqual(mde.TracRef1().sub('[#100]'), '[#100]')
        self.assertEqual(mde.TracRef1().sub('[r123]'), '[r123]')

    def test_word_boundaries(self):
        self.assertEqual(mde.TracRef1().sub('foo#100'), 'foo#100')
        self.assertEqual(mde.TracRef1().sub('r123bar'), 'r123bar')

    @mock.patch('allura.lib.markdown_extensions.M.Shortlink.lookup')
    def test_legit_refs(self, lookup):
        shortlink = mock.Mock(url='/p/project/tool/artifact')
        shortlink.ref.artifact.deleted = False
        lookup.return_value = shortlink
        self.assertEqual(mde.TracRef1().sub('#100'),
                         '[#100](/p/project/tool/artifact)')
        self.assertEqual(mde.TracRef1().sub('r123'),
                         '[r123](/p/project/tool/artifact)')


class TestTracRef2(unittest.TestCase):

    @mock.patch('allura.lib.markdown_extensions.M.Shortlink.lookup')
    def test_no_such_artifact(self, lookup):
        lookup.return_value = None
        self.assertEqual(mde.TracRef2().sub('ticket:100'), 'ticket:100')

    def test_word_boundaries(self):
        self.assertEqual(mde.TracRef2().sub('myticket:100'), 'myticket:100')
        self.assertEqual(mde.TracRef2().sub('ticket:100th'), 'ticket:100th')

    @mock.patch('allura.lib.markdown_extensions.M.Shortlink.lookup')
    def test_legit_refs(self, lookup):
        shortlink = mock.Mock(url='/p/project/tool/artifact/')
        shortlink.ref.artifact.deleted = False
        lookup.return_value = shortlink
        pattern = mde.TracRef2()
        pattern.get_comment_slug = lambda *args: 'abc'
        self.assertEqual(pattern.sub('ticket:100'),
                         '[ticket:100](/p/project/tool/artifact/)')
        self.assertEqual(pattern.sub('[ticket:100]'),
                         '[[ticket:100](/p/project/tool/artifact/)]')
        self.assertEqual(pattern.sub('comment:13:ticket:100'),
                         '[comment:13:ticket:100](/p/project/tool/artifact/#abc)')
        pattern.get_comment_slug = lambda *args: None
        self.assertEqual(pattern.sub('comment:13:ticket:100'),
                         '[comment:13:ticket:100](/p/project/tool/artifact/)')


class TestTracRef3(unittest.TestCase):

    def test_no_app_context(self):
        self.assertEqual(mde.TracRef3(None)
                         .sub('source:file.py'), 'source:file.py')

    def test_legit_refs(self):
        app = mock.Mock(url='/p/project/tool/')
        self.assertEqual(mde.TracRef3(app).sub('source:file.py'),
                         '[source:file.py](/p/project/tool/HEAD/tree/file.py)')
        self.assertEqual(mde.TracRef3(app).sub('source:file.py@123'),
                         '[source:file.py@123](/p/project/tool/123/tree/file.py)')
        self.assertEqual(mde.TracRef3(app).sub('source:file.py@123#L456'),
                         '[source:file.py@123#L456](/p/project/tool/123/tree/file.py#l456)')
        self.assertEqual(mde.TracRef3(app).sub('source:file.py#L456'),
                         '[source:file.py#L456](/p/project/tool/HEAD/tree/file.py#l456)')


class TestPatternReplacingProcessor(unittest.TestCase):

    @mock.patch('allura.lib.markdown_extensions.M.Shortlink.lookup')
    def test_run(self, lookup):
        shortlink = mock.Mock(url='/p/project/tool/artifact')
        shortlink.ref.artifact.deleted = False
        lookup.return_value = shortlink
        p = mde.PatternReplacingProcessor(mde.TracRef1(), mde.TracRef2())
        res = p.run(['#100', 'ticket:100'])
        self.assertEqual(res, [
            '[#100](/p/project/tool/artifact)',
            '[ticket:100](/p/project/tool/artifact)'])


class TestCommitMessageExtension(unittest.TestCase):

    @mock.patch('allura.lib.markdown_extensions.TracRef2.get_comment_slug')
    @mock.patch('allura.lib.markdown_extensions.M.Shortlink.lookup')
    def test_convert(self, lookup, get_comment_slug):
        from allura.lib.app_globals import ForgeMarkdown

        shortlink = mock.Mock(url='/p/project/tool/artifact/')
        shortlink.ref.artifact.deleted = False
        lookup.return_value = shortlink
        get_comment_slug.return_value = 'abc'
        app = mock.Mock(url='/p/project/tool/')

        text = """\
# Not A Heading #
---
* #100, r2
* ticket:100
* comment:13:ticket:2
* source:test.py@2#L3

Not *strong* or _underlined_."""

        expected_html = """\
<div class="markdown_content"><p># Not A Heading #<br>
---<br>
* <a href="/p/project/tool/artifact/">#100</a>, <a href="/p/project/tool/artifact/">r2</a><br>
* <a href="/p/project/tool/artifact/">ticket:100</a><br>
* <a href="/p/project/tool/artifact/#abc">comment:13:ticket:2</a><br>
* <a href="/p/project/tool/2/tree/test.py#l3">source:test.py@2#L3</a></p>
<p>Not *strong* or _underlined_.</div>"""

        md = ForgeMarkdown(
            extensions=[mde.CommitMessageExtension(app), 'markdown.extensions.nl2br'],
            output_format='html')
        self.assertEqual(md.convert(text), expected_html)
