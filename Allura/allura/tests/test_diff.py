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

from allura.lib.diff import HtmlSideBySideDiff


class TestHtmlSideBySideDiff:

    # these tests are representative but not complete
    # there are a lot of different nuanced situations (e.g. trailing blanks etc)
    # and manually testing after changes is recommended too

    def test_make_table(self):
        a = 'line A1\nline 2\nline 3'.splitlines(keepends=True)
        b = 'line 1B\nline X\ntotalchg\n\tnew<script>&"'.splitlines(keepends=True)
        expected = '''\
<table class="side-by-side-diff">
  <thead>
    <th class="lineno"></th>
    <th>file a</th>
    <th class="lineno"></th>
    <th>file b</th>
  </thead>
<tr>
  <td class="lineno">1</td>
  <td class="diff-chg"><pre>line <span class="diff-rem">A</span>1</pre></td>
  <td class="lineno">1</td>
  <td class="diff-chg"><pre>line 1<span class="diff-add">B</span></pre></td>
</tr>
<tr>
  <td class="lineno">2</td>
  <td class="diff-chg"><pre>line <span class="diff-rem">2</span></pre></td>
  <td class="lineno">2</td>
  <td class="diff-chg"><pre>line <span class="diff-add">X</span></pre></td>
</tr>
<tr>
  <td class="lineno">3</td>
  <td class="diff-rem"><pre>line 3</pre></td>
  <td class="lineno">3</td>
  <td class="diff-add"><pre>totalchg</pre></td>
</tr>
<tr>
  <td class="lineno"></td>
  <td><pre></pre></td>
  <td class="lineno">4</td>
  <td class="diff-add"><pre>    new&lt;script&gt;&amp;&quot;</pre></td>
</tr>
</table>
'''.strip()
        html = HtmlSideBySideDiff().make_table(a, b, 'file a', 'file b').strip()
        assert html == expected

    def test_make_table_context_gap_start(self):
        a = 'line 1\nline 2\nline 3\nline 4\n line 5\nline 6\nline 7\nline 8'.splitlines(keepends=True)
        b = 'line 1\nline 2\nline 3\nline 4\n line 5\nline 6\nline X\nline 8'.splitlines(keepends=True)
        start = '''\
<table class="side-by-side-diff">
  <thead>
    <th class="lineno"></th>
    <th>file a</th>
    <th class="lineno"></th>
    <th>file b</th>
  </thead>
<tr>
  <td class="lineno"></td>
  <td class="diff-gap"><pre>...</pre></td>
  <td class="lineno"></td>
  <td class="diff-gap"><pre>...</pre></td>
</tr>
<tr>
  <td class="lineno">2</td>
  <td><pre>line 2</pre></td>
  <td class="lineno">2</td>
  <td><pre>line 2</pre></td>
</tr>
'''.strip()  # more lines follow in full output

        html = HtmlSideBySideDiff().make_table(a, b, 'file a', 'file b').strip()
        assert start in html

    def test_make_table_context_gap_middle(self):
        a = 'line 1\nline 2\nline 3\nline 4\n line 5\nline 6\nline 7\nline 8\nline 9\nline 10\nline 11\nline 12\nline 13'.splitlines(keepends=True)
        b = 'line X\nline 2\nline 3\nline 4\n line 5\nline 6\nline 7\nline 8\nline 9\nline 10\nline 11\nline 12\nline Y'.splitlines(keepends=True)
        middle = '''\
<tr>
  <td class="lineno">6</td>
  <td><pre>line 6</pre></td>
  <td class="lineno">6</td>
  <td><pre>line 6</pre></td>
</tr>
<tr>
  <td class="lineno"></td>
  <td class="diff-gap"><pre>...</pre></td>
  <td class="lineno"></td>
  <td class="diff-gap"><pre>...</pre></td>
</tr>
<tr>
  <td class="lineno">8</td>
  <td><pre>line 8</pre></td>
  <td class="lineno">8</td>
  <td><pre>line 8</pre></td>
</tr>
'''.strip()
        html = HtmlSideBySideDiff().make_table(a, b, 'file a', 'file b').strip()
        assert middle in html

    def test_unicode_make_table(self):
        a = ['строка']
        b = ['измененная строка']
        html = HtmlSideBySideDiff().make_table(a, b, 'file a', 'file b')
        assert 'строка' in html
