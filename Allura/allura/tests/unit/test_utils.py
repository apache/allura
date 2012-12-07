import unittest
from mock import Mock

from alluratest.controller import setup_unit_test
from allura.lib.utils import generate_code_stats, chunked_list
from allura.lib.diff import HtmlSideBySideDiff


class TestCodeStats(unittest.TestCase):

    def setUp(self):
        setup_unit_test()

    def test_generate_code_stats(self):
        blob = Mock()
        blob.text = \
"""class Person(object):

    def __init__(self, name='Alice'):
        self.name = name

    def greetings(self):
        print "Hello, %s" % self.name
\t\t"""
        blob.size = len(blob.text)

        stats = generate_code_stats(blob)
        assert stats['line_count'] == 8
        assert stats['data_line_count'] == 5
        assert stats['code_size'] == len(blob.text)


class TestUtils(unittest.TestCase):
    def test_chunked_list(self):
        l = range(10)
        chunks = list(chunked_list(l, 3))
        self.assertEqual(len(chunks), 4)
        self.assertEqual(len(chunks[0]), 3)
        self.assertEqual([el for sublist in chunks for el in sublist], l)


class TestHtmlSideBySideDiff(unittest.TestCase):

    def setUp(self):
        self.diff = HtmlSideBySideDiff()

    def test_render_change(self):
        html = self.diff._render_change(
                'aline', 'aline <span class="diff-add">bline</span>',
                1, 2,'aclass', 'bclass')
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
    <th colspan="2">file a</th>
    <th colspan="2">file b</th>
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
