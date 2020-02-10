# -*- coding: utf-8 -*-
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

from __future__ import unicode_literals
from __future__ import absolute_import
import unittest

from allura.lib.diff import HtmlSideBySideDiff


class TestHtmlSideBySideDiff(unittest.TestCase):

    def setUp(self):
        self.diff = HtmlSideBySideDiff()

    def test_render_change(self):
        html = self.diff._render_change(
            'aline', 'aline <span class="diff-add">bline</span>',
            1, 2, 'aclass', 'bclass')
        expected = '''
<tr>
  <td class="lineno">1</td>
  <td class="aclass"><pre>aline</pre></td>
  <td class="lineno">2</td>
  <td class="bclass"><pre>aline <span class="diff-add">bline</span></pre></td>
</tr>'''.strip()
        self.assertEqual(html, expected)

    def test_render_change_default_args(self):
        html = self.diff._render_change('aline', 'bline')
        expected = '''
<tr>
  <td class="lineno"></td>
  <td><pre>aline</pre></td>
  <td class="lineno"></td>
  <td><pre>bline</pre></td>
</tr>'''.strip()
        self.assertEqual(html, expected)

    def test_preprocess(self):
        d = self.diff
        self.assertEquals(d._preprocess(None), None)
        self.assertEquals(d._preprocess('<br>&nbsp;'), '&lt;br&gt;&amp;nbsp;')
        self.assertEquals(d._preprocess('\ttabbed'), '    tabbed')
        # test non default tab size
        d = HtmlSideBySideDiff(2)
        self.assertEquals(d._preprocess('\ttabbed'), '  tabbed')

    def test_replace_marks(self):
        line, flag = self.diff._replace_marks('\0+line added\1')
        self.assertEquals(line, 'line added')
        self.assertEquals(flag, 'diff-add')
        line, flag = self.diff._replace_marks('\0-line removed\1')
        self.assertEquals(line, 'line removed')
        self.assertEquals(flag, 'diff-rem')
        line, flag = self.diff._replace_marks('\0^line changed\1')
        self.assertEquals(line, '<span class="diff-chg">line changed</span>')
        self.assertEquals(flag, 'diff-chg')
        line, flag = self.diff._replace_marks('chunk \0+add\1ed')
        self.assertEquals(line, 'chunk <span class="diff-add">add</span>ed')
        self.assertEquals(flag, 'diff-chg')
        line, flag = self.diff._replace_marks('chunk \0-remov\1ed')
        self.assertEquals(line, 'chunk <span class="diff-rem">remov</span>ed')
        self.assertEquals(flag, 'diff-chg')
        line, flag = self.diff._replace_marks('chunk \0^chang\1ed')
        self.assertEquals(line, 'chunk <span class="diff-chg">chang</span>ed')
        self.assertEquals(flag, 'diff-chg')

    def test_make_line(self):
        # context separation
        d = (None, None, None)
        expected = '''
<tr>
  <td class="lineno"></td>
  <td class="diff-gap"><pre>...</pre></td>
  <td class="lineno"></td>
  <td class="diff-gap"><pre>...</pre></td>
</tr>'''.strip()
        self.assertEquals(self.diff._make_line(d), expected)
        # no change
        d = ((1, 'aline'), (1, 'aline'), False)
        expected = '''
<tr>
  <td class="lineno">1</td>
  <td><pre>aline</pre></td>
  <td class="lineno">1</td>
  <td><pre>aline</pre></td>
</tr>'''.strip()
        self.assertEquals(self.diff._make_line(d), expected)
        # has change
        d = ((1, '\0^a\1line'), (1, '\0^b\1line'), True)
        expected = '''
<tr>
  <td class="lineno">1</td>
  <td class="diff-chg"><pre><span class="diff-chg">a</span>line</pre></td>
  <td class="lineno">1</td>
  <td class="diff-chg"><pre><span class="diff-chg">b</span>line</pre></td>
</tr>'''.strip()
        self.assertEquals(self.diff._make_line(d), expected)

    def test_make_table(self):
        a = 'line 1\nline 2'.split('\n')
        b = 'changed line 1\nchanged line 2'.split('\n')
        expected = '''
<table class="side-by-side-diff">
  <thead>
    <th class="lineno"></th>
    <th>file a</th>
    <th class="lineno"></th>
    <th>file b</th>
  </thead>
<tr>
  <td class="lineno">1</td>
  <td class="diff-rem"><pre>line 1</pre></td>
  <td class="lineno">1</td>
  <td class="diff-add"><pre>changed line 1</pre></td>
</tr>
<tr>
  <td class="lineno">2</td>
  <td class="diff-rem"><pre>line 2</pre></td>
  <td class="lineno">2</td>
  <td class="diff-add"><pre>changed line 2</pre></td>
</tr>
</table>
'''.strip()
        html = self.diff.make_table(a, b, 'file a', 'file b')
        self.assertEquals(html, expected)

    def test_unicode_make_table(self):
        a = ['строка']
        b = ['измененная строка']
        html = self.diff.make_table(a, b, 'file a', 'file b')
        assert 'строка' in html
