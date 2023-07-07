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
from __future__ import annotations

import html
import contextlib
import logging
from collections.abc import Iterable, Generator

import sxsdiff
from diff_match_patch import diff_match_patch
import six
from sxsdiff.calculator import LineChange, ElementsHolder, PlainElement, AdditionElement, DeletionElement

log = logging.getLogger(__name__)

# There are a few cases where we get empty trailing '' elements.  Maybe a bug within sxsdiff.calculator?
# we work around them, using these constants in a few places below
emptyUnchangedElem = PlainElement('')
spaceUnchangedElem = PlainElement(' ')
emptyAddElem = AdditionElement('')
emptyDelElem = DeletionElement('')


def is_single_chg(chg_parts: ElementsHolder) -> bool:
    return len(chg_parts) <= 1 or (
        len(chg_parts) == 2 and chg_parts.elements[-1] in [emptyUnchangedElem, spaceUnchangedElem]
    )


class SxsOutputGenerator(sxsdiff.BaseGenerator):
    # based on sxsdiff.generators.github.GitHubStyledGenerator

    table_tmpl_start = '''
<table class="side-by-side-diff">
  <thead>
    <th class="lineno"></th>
    <th>%s</th>
    <th class="lineno"></th>
    <th>%s</th>
  </thead>
'''.strip()

    table_tmpl_end = '</table>'

    def __init__(self, adesc: str, bdesc: str):
        self.adesc = adesc
        self.bdesc = bdesc

    def _spit(self, content):
        self.out += content + '\n'

    def run(self, diff_result: Iterable[LineChange | None]):
        self.out = ''
        super().run(diff_result)
        return self.out

    def visit_row(self, line_change: LineChange | None):
        if line_change is None:
            self._spit_context_marker()
            self._spit_context_marker()
        elif not line_change.changed:
            self._spit_unchanged_side(line_change.left_no, line_change.left)
            self._spit_unchanged_side(line_change.right_no, line_change.right)
        else:
            whole_line_changed = is_single_chg(line_change.left) and is_single_chg(line_change.right)
            self._spit_changed_side('diff-rem' if whole_line_changed else 'diff-chg',
                                    line_change.left_no, line_change.left)
            self._spit_changed_side('diff-add' if whole_line_changed else 'diff-chg',
                                    line_change.right_no, line_change.right)

    @contextlib.contextmanager
    def wrap_row(self, line_change):
        self._spit('<tr>')
        yield
        self._spit('</tr>')

    @contextlib.contextmanager
    def wrap_result(self, sxs_result):
        self._spit(self.table_tmpl_start % (self.adesc, self.bdesc))
        yield
        self._spit(self.table_tmpl_end)

    def _spit_context_marker(self):
        context = {
            'mode': 'diff-gap',
            'lineno': '',
            'code': '...',
        }
        self._spit_side_from_context(context)

    def _spit_unchanged_side(self, lineno, holder):
        context = {
            'mode': 'context',
            'lineno': lineno,
            'code': html.escape(str(holder)),
        }
        self._spit_side_from_context(context)

    def _spit_changed_side(self, mode, lineno, holder):
        if not holder:
            self._spit_side_from_context({'lineno': '', 'code': '', 'mode': ''})
            return

        bits = []
        for elem in holder.elements:
            piece = html.escape(str(elem))
            if elem.is_changed and not is_single_chg(holder):
                if elem.flag == diff_match_patch.DIFF_INSERT:
                    clss = 'diff-add'
                elif elem.flag == diff_match_patch.DIFF_DELETE:
                    clss = 'diff-rem'
                else:
                    clss = ''
                bits.append(f'<span class="{clss}">{piece}</span>')
            else:
                bits.append(piece)
        code = ''.join(bits)

        context = {
            'mode': mode,
            'lineno': lineno,
            'code': code,
        }
        self._spit_side_from_context(context)

    def _spit_side_from_context(self, context):
        self._spit(f'  <td class="lineno">{context["lineno"]}</td>')
        mode = context['mode']
        clss = (' class="%s"' % mode) if mode not in ['context', ''] else ''
        self._spit(f'  <td{clss}><pre>{context["code"]}</pre></td>')


def sxsdiff_cleanup_trailing(input_lines: Iterable[LineChange]) -> Iterable[LineChange]:
    cleaned_lines = list(input_lines)
    if not cleaned_lines:
        return []
    lastline = cleaned_lines[-1]
    if (
            (lastline.left.elements == [emptyUnchangedElem] and lastline.right.elements == [emptyUnchangedElem]) or
            (lastline.left.elements == [] and lastline.right.elements == [emptyAddElem]) or
            (lastline.left.elements == [emptyDelElem] and lastline.right.elements == [])
    ):
        cleaned_lines.pop()
    return cleaned_lines


def update_with_context_chunks(input_lines: Iterable[LineChange], num_context: int) -> Iterable[LineChange | None]:
    """
    Remove identical lines, except several around any changed lines
    """
    lines_with_flag: list[list] = []  # [LineChange, bool] in each item
    changed_line_idxs: list[int] = []

    for current_line, line in enumerate(input_lines):
        lines_with_flag.append([line, False])
        if line.changed:
            changed_line_idxs.append(current_line)

    for changed_line_idx in changed_line_idxs:
        for context_idx in range(changed_line_idx-num_context, changed_line_idx+num_context+1):
            try:
                lines_with_flag[context_idx][1] = True
            except IndexError:
                pass

    output_lines: list[LineChange | None] = []
    prev_was_shown = True
    for line, show in lines_with_flag:
        if show:
            if not prev_was_shown:
                output_lines.append(None)
            output_lines.append(line)

        prev_was_shown = show

    return output_lines


class HtmlSideBySideDiff:

    def make_table(self, a: list[str], b: list[str], adesc=None, bdesc=None, context=5, tabsize=4) -> str:
        """Make html table that displays side-by-side diff

        Arguments:
         - a -- list of text lines with \n, to be compared to b
         - b -- list of text lines with \n, to be compared to a
         - adesc -- description of the 'a' lines (e.g. filename)
         - bdesc -- description of the 'b' lines (e.g. filename)
         - context -- number of context lines to display

        Uses sxsdiff/diff_match_patch which has much better performance than stdlib htmldiff/_mdiff
            https://github.com/python/cpython/issues/51180
        """
        adesc = six.ensure_text(adesc) or ''
        bdesc = six.ensure_text(bdesc) or ''

        atext = ''.join(a).expandtabs(tabsize)
        btext = ''.join(b).expandtabs(tabsize)

        sxsdiff_result = sxsdiff.DiffCalculator().run(atext, btext)
        sxsdiff_cleaned = sxsdiff_cleanup_trailing(sxsdiff_result)
        sxsdiff_with_contexts = update_with_context_chunks(sxsdiff_cleaned, context)

        return SxsOutputGenerator(adesc, bdesc).run(sxsdiff_with_contexts)
