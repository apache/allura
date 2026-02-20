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
import re
import logging
import warnings
import xml.etree.ElementTree as etree
import os

from urllib.parse import urljoin

from tg import config
from tg import tmpl_context as c
from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning
import html5lib
import html5lib.serializer
import html5lib.filters.alphabeticalattributes
import markdown
import markdown.inlinepatterns
import markdown.util
import emoji
from markupsafe import Markup

from . import macro
from . import helpers as h
from allura import model as M
from allura.lib.utils import ForgeHTMLSanitizerFilter, is_nofollow_url

log = logging.getLogger(__name__)


MACRO_PATTERN = r'\[\[([^\]\[]+)\]\]'


def clear_markdown_registry(reg: markdown.util.Registry, keep: list[str] = []):
    keep_items = {}
    for name in keep:
        keep_items[name] = reg[name]

    # this resets Registry's internal data structures to be empty
    reg.__init__()

    for name, item in keep_items.items():
        reg.register(item, name, 50)  # arbitrary priority :(


class CommitMessageExtension(markdown.Extension):

    """Markdown extension for processing commit messages.

    People don't expect their commit messages to be parsed as Markdown. This
    extension is therefore intentionally minimal in what it does. It knows how
    to handle Trac-style short refs, will replace short refs with links, and
    will create paragraphs around double-line breaks. That is *all* it does.

    To make it do more, re-add some inlinePatterns and/or blockprocessors.

    Some examples of the Trac-style refs this extension can parse::

        #100
        r123
        ticket:100
        comment:13:ticket:100
        source:path/to/file.c@123#L456 (rev 123, lineno 456)

    Trac-style refs will be converted to links to the appropriate artifact by
    the :class:`PatternReplacingProcessor` preprocessor.

    """

    def __init__(self, app):
        super().__init__()
        self.app = app
        self._use_wiki = False

    def extendMarkdown(self, md):
        md.registerExtension(self)
        # remove default preprocessors and add our own
        clear_markdown_registry(md.preprocessors)

        # The last param of .register() is priority. Higher vals go first.

        md.preprocessors.register(PatternReplacingProcessor(TracRef1(), TracRef2(), TracRef3(self.app)), 'trac_refs', 0)

        # remove all inlinepattern processors except short refs and links
        clear_markdown_registry(md.inlinePatterns, keep=['link'])
        md.inlinePatterns.register(ForgeShortRefPattern(markdown.inlinepatterns.REFERENCE_RE, md, ext=self), 'short_reference', 0)

        # remove all default block processors except for paragraph
        clear_markdown_registry(md.parser.blockprocessors, keep=['paragraph'])
        # wrap artifact link text in square brackets
        self.forge_link_tree_processor = ForgeLinkTreeProcessor(md)
        md.treeprocessors.register(self.forge_link_tree_processor, 'links', 0)

        # Sanitize HTML
        md.postprocessors.register(HTMLSanitizer(), 'sanitize_html', 3)
        # Put a class around markdown content for custom css
        md.postprocessors.register(AddCustomClass(), 'add_custom_class', 2)
        md.postprocessors.register(MarkAsSafe(), 'mark_safe', 1)

    def reset(self):
        self.forge_link_tree_processor.reset()


class Pattern:

    """Base class for regex patterns used by the :class:`PatternReplacingProcessor`.

    Subclasses must define :attr:`pattern` (a compiled regex), and
    :meth:`repl`.

    """
    BEGIN, END = r'(^|\b|\s)', r'($|\b|\s)'

    def sub(self, line):
        return self.pattern.sub(self.repl, line)

    def repl(self, match):
        """Return a string to replace ``match`` in the source string (the
        string in which the match was found).

        """
        return match.group()


class TracRef1(Pattern):

    """Replaces Trac-style short refs with links. Example patterns::

        #100 (ticket 100)
        r123 (revision 123)

    """
    pattern = re.compile(r'(?<!\[|\w)([#r]\d+)(?!\]|\w)')

    def repl(self, match):
        shortlink = M.Shortlink.lookup(match.group(1))
        if shortlink and not getattr(shortlink.ref.artifact, 'deleted', False):
            return '[{ref}]({url})'.format(
                ref=match.group(1),
                url=shortlink.url)
        return match.group()


class TracRef2(Pattern):

    """Replaces Trac-style short refs with links. Example patterns::

        ticket:100
        comment:13:ticket:400

    """
    pattern = re.compile(
        Pattern.BEGIN + r'((comment:(\d+):)?(ticket:)(\d+))' + Pattern.END)

    def repl(self, match):
        shortlink = M.Shortlink.lookup('#' + match.group(6))
        if shortlink and not getattr(shortlink.ref.artifact, 'deleted', False):
            url = shortlink.url
            if match.group(4):
                slug = self.get_comment_slug(
                    shortlink.ref.artifact, match.group(4))
                slug = '#' + slug if slug else ''
                url = url + slug

            return '{front}[{ref}]({url}){back}'.format(
                front=match.group(1),
                ref=match.group(2),
                url=url,
                back=match.group(7))
        return match.group()

    def get_comment_slug(self, ticket, comment_num):
        """Given the id of an imported Trac comment, return it's Allura slug.

        """
        if not ticket:
            return None

        comment_num = int(comment_num)
        comments = ticket.discussion_thread.post_class().query.find(dict(
            discussion_id=ticket.discussion_thread.discussion_id,
            thread_id=ticket.discussion_thread._id,
            status={'$in': ['ok', 'pending']},
            deleted=False)).sort('timestamp')

        if comment_num <= comments.count():
            return comments.all()[comment_num - 1].slug


class TracRef3(Pattern):

    """Replaces Trac-style short refs with links. Example patterns::

        source:trunk/server/file.c@123#L456 (rev 123, lineno 456)

    Creates a link to a specific line of a source file at a specific revision.

    """
    pattern = re.compile(
        Pattern.BEGIN + r'((source:)([^@#\s]+)(@(\w+))?(#L(\d+))?)' + Pattern.END)

    def __init__(self, app):
        super(Pattern, self).__init__()
        self.app = app

    def repl(self, match):
        if not self.app:
            return match.group()
        file, rev, lineno = (
            match.group(4),
            match.group(6) or 'HEAD',
            '#l' + match.group(8) if match.group(8) else '')
        url = '{app_url}{rev}/tree/{file}{lineno}'.format(
            app_url=self.app.url,
            rev=rev,
            file=file,
            lineno=lineno)
        return '{front}[{ref}]({url}){back}'.format(
            front=match.group(1),
            ref=match.group(2),
            url=url,
            back=match.group(9))


class PatternReplacingProcessor(markdown.preprocessors.Preprocessor):

    """A Markdown preprocessor that searches the source lines for patterns and
    replaces matches with alternate text.

    """

    def __init__(self, *patterns):
        self.patterns = patterns or []

    def run(self, lines):
        new_lines = []
        for line in lines:
            for pattern in self.patterns:
                line = pattern.sub(line)
            new_lines.append(line)
        return new_lines


class ForgeExtension(markdown.Extension):

    def __init__(self, wiki=False, email=False, macro_context=None):
        super().__init__()
        self._use_wiki = wiki
        self._is_email = email
        self._macro_context = macro_context

    def extendMarkdown(self, md):
        md.registerExtension(self)
        md.preprocessors.register(ForgeMacroIncludePreprocessor(md), 'macro_include', -99)

        # The last param of .register() is priority. Higher vals go first.

        # this has to be before the 'escape' processor, otherwise weird
        # placeholders are inserted for escaped chars within urls, and then the
        # autolink can't match the whole url
        md.inlinePatterns.register(AutolinkPattern(r'(?:(?<=\s)|^)(http(?:s?)://[a-zA-Z0-9./\-\\_%?&=+#;~:!@]+)', md),
                                   'autolink_without_brackets',
                                   185)  # was '<escape' and 'escape' is priority 180; great num runs first, so: 185
        # replace the 2 link processors with our extended versions
        md.inlinePatterns.register(ForgeLinkPattern(markdown.inlinepatterns.LINK_RE, md, ext=self), 'link', 160)  # [WikiPage](foobar) or [WikiPage](foobar "title")
        md.inlinePatterns.register(ForgeShortRefPattern(markdown.inlinepatterns.REFERENCE_RE, md, ext=self), 'short_reference', 130)  # [WikiPage] no parens

        # macro must be processed before links
        md.inlinePatterns.register(ForgeMacroPattern(MACRO_PATTERN, md, ext=self), 'macro', 165)  # similar to above

        self.forge_link_tree_processor = ForgeLinkTreeProcessor(md)
        md.treeprocessors.register(self.forge_link_tree_processor, 'links', 0)
        # Sanitize HTML
        md.postprocessors.register(HTMLSanitizer(), 'sanitize_html', 5)
        # Rewrite all relative links that don't start with . to have a '../' prefix
        md.postprocessors.register(RelativeLinkRewriter(make_absolute=self._is_email), 'rewrite_relative_links', 4)
        # Put a class around markdown content for custom css
        md.postprocessors.register(AddCustomClass(), 'add_custom_class', 3)
        md.postprocessors.register(MarkAsSafe(), 'mark_safe', 2)

    def reset(self):
        self.forge_link_tree_processor.reset()


class EmojiExtension(markdown.Extension):

    EMOJI_RE = r'(:[a-zA-Z0-9\+\-_&.ô’Åéãíç()!#\*]+:)'

    def extendMarkdown(self, md):
        md.registerExtension(self)
        md.inlinePatterns.register(EmojiInlinePattern(self.EMOJI_RE), 'emoji', 0)


class EmojiInlinePattern(markdown.inlinepatterns.InlineProcessor):

    def handleMatch(self, m: re.Match[str], data: str) -> tuple[etree.Element | str | None, int | None, int | None]:
        emoji_code = m.group(1)
        return emoji.emojize(emoji_code, language="alias"), m.start(0), m.end(0)


class UserMentionExtension(markdown.Extension):

    UM_RE = r'\B(@(?![0-9]+$)(?!-)[a-z0-9_-]{2,14}[a-z0-9_])'

    def extendMarkdown(self, md):
        md.registerExtension(self)
        md.inlinePatterns.register(UserMentionInlinePattern(self.UM_RE), 'user_mentions', 0)


class UserMentionInlinePattern(markdown.inlinepatterns.InlineProcessor):

    def handleMatch(self, m: re.Match[str], data: str) -> tuple[etree.Element | str | None, int | None, int | None]:
        user_name = m.group(1).replace("@", "")
        user = M.User.by_username(user_name)
        result = None

        if user and not user.pending and not user.disabled:
            result = etree.Element('a')
            result.text = "@%s" % user_name
            result.set('href', h.username_project_url(user))
            result.set('class', 'user-mention')
        else:
            result = "@%s" % user_name
        return result, m.start(0), m.end(0)


artifact_re = re.compile(r'((.*?):)?((.*?):)?(.+)')


class ForgeShortRefPattern(markdown.inlinepatterns.ShortReferenceInlineProcessor):

    def __init__(self, *args, **kwargs):
        self.ext = kwargs.pop('ext')
        super().__init__(*args, **kwargs)

    def handleMatch(self, m: re.Match[str], data: str) -> tuple[etree.Element | None, int | None, int | None]:
        text, index, handled = self.getText(data, m.end(0))
        if not handled:
            return None, None, None
        if text == 'TOC':
            return None, None, None

        if artifact_re.match(text) and c.project:
            href, classes = _expand_alink(self.ext, text, is_link_with_brackets=True)
            if 'notfound' in classes and not self.ext._use_wiki:
                el = etree.Element('span')
                el.text = '[%s]' % text
            else:
                el = self.makeTag(href, title='', text=text)
                if classes:
                    el.set('class', classes)
            end = index
            return el, m.start(0), end
        else:
            return None, None, None


class ForgeLinkPattern(markdown.inlinepatterns.LinkInlineProcessor):

    def __init__(self, *args, **kwargs):
        self.ext = kwargs.pop('ext')
        self.extra_allura_classes = ''
        super().__init__(*args, **kwargs)

    def getLink(self, data, index) -> tuple[str, str | None, int, bool]:
        href, title, index, handled = super().getLink(data, index)

        if artifact_re.match(href) and c.project:
            href, self.extra_allura_classes = _expand_alink(self.ext, href, is_link_with_brackets=False)
            # TODO: some thread-local var instead of self.extra_allura_classes for thread safety?

        return href, title, index, handled

    def handleMatch(self, m: re.Match[str], data: str) -> tuple[etree.Element | None, int | None, int | None]:
        el, start, end = super().handleMatch(m, data)
        if el is not None and self.extra_allura_classes:
            el.set('class', self.extra_allura_classes)
            self.extra_allura_classes = ''  # reset for next link
        return el, start, end


def _expand_alink(ext: markdown.Extension, link: str, is_link_with_brackets: bool) -> tuple[str, str]:
    '''Return (href, classes) for an artifact link'''
    classes = ''
    if is_link_with_brackets:
        classes = 'alink'
    href = link
    shortlink = M.Shortlink.lookup(link)
    if shortlink and shortlink.ref and not getattr(shortlink.ref.artifact, 'deleted', False):
        href = shortlink.url
        if getattr(shortlink.ref.artifact, 'is_closed', False):
            classes += ' strikethrough'
        ext.forge_link_tree_processor.alinks.append(shortlink)
    elif is_link_with_brackets:
        href = h.urlquote(link)
        classes += ' notfound'
    attach_link = link.split('/attachment/')
    if len(attach_link) == 2 and ext._use_wiki:
        shortlink = M.Shortlink.lookup(attach_link[0])
        if shortlink:
            attach_status = ' notfound'
            for attach in shortlink.ref.artifact.attachments:
                if attach.filename == attach_link[1]:
                    attach_status = ''
            classes += attach_status
    return href, classes


class ForgeMacroPattern(markdown.inlinepatterns.InlineProcessor):

    def __init__(self, *args, **kwargs):
        self.ext = kwargs.pop('ext')
        self.macro = macro.parse(self.ext._macro_context)
        super().__init__(*args, **kwargs)

    def handleMatch(self, m: re.Match[str], data: str) -> tuple[etree.Element | str | None, int | None, int | None]:
        html = self.macro(m.group(1))
        placeholder = self.md.htmlStash.store(html)
        return placeholder, m.start(0), m.end(0)


class ForgeLinkTreeProcessor(markdown.treeprocessors.Treeprocessor):
    '''
    Wraps artifact links with [] and tracks those artifact links for search.find_shortlinks

    The 'alink' class itself is not currently needed for any JS/CSS but ends up in HTML anyway
    '''

    def __init__(self, parent):
        self.parent = parent
        self.alinks = []

    def run(self, root):
        for node in root.iter('a'):
            if 'alink' in node.get('class', '').split() and node.text:
                node.text = '[' + node.text + ']'
        return root

    def reset(self):
        self.alinks = []


class MarkAsSafe(markdown.postprocessors.Postprocessor):

    def run(self, text):
        return Markup(text)  # noqa: S704


class AddCustomClass(markdown.postprocessors.Postprocessor):

    def run(self, text):
        return '<div class="markdown_content">%s</div>' % text


class RelativeLinkRewriter(markdown.postprocessors.Postprocessor):

    def __init__(self, make_absolute=False):
        self._make_absolute = make_absolute

    def run(self, text: str):
        with warnings.catch_warnings():
            # sometimes short snippets of code (especially escaped html) can trigger this
            warnings.filterwarnings('ignore', category=MarkupResemblesLocatorWarning)

            soup = BeautifulSoup(text,
                                 'html5lib')  # 'html.parser' parser gives weird </li> behaviour with test_macro_members
        if self._make_absolute:
            rewrite = self._rewrite_abs
        else:
            rewrite = self._rewrite
        for link in soup.find_all('a'):
            rewrite(link, 'href')
        for link in soup.find_all('img'):
            rewrite(link, 'src')

        # html5lib parser adds html/head/body tags, so output <body> without its own tags
        return str(soup.body)[len('<body>'):-len('</body>')]

    def _rewrite(self, tag, attr):
        val = tag.get(attr)
        if val is None:
            return
        if ' ' in val:
            # Don't urllib.quote to avoid possible double-quoting
            # just make sure no spaces
            val = val.replace(' ', '%20')
            tag[attr] = val
        if 'markdown_syntax' in val:
            tag['rel'] = 'nofollow'
        if '://' in val:
            if is_nofollow_url(val):
                tag['rel'] = 'nofollow'
            return
        if val.startswith('/'):
            return
        if val.startswith('.'):
            return
        if val.startswith('mailto:'):
            return
        if val.startswith('#'):
            return
        if val.startswith('../') or val.startswith('./'):
            return
        # if none of the above, assume relative to directory link
        val = os.path.join('.', val)
        tag[attr] = val

    def _rewrite_abs(self, tag, attr):
        self._rewrite(tag, attr)
        val = tag.get(attr)
        val = urljoin(config['base_url'], val)
        tag[attr] = val


class HTMLSanitizer(markdown.postprocessors.Postprocessor):

    def run(self, text):
        parsed = html5lib.parseFragment(text)

        # if we didn't have to customize our sanitization, could just do:
        # return html5lib.serialize(parsed, sanitize=True)

        # instead we do the same steps as that function,
        # but add our ForgeHTMLSanitizerFilter instead of sanitize=True which would use the standard one
        TreeWalker = html5lib.treewalkers.getTreeWalker("etree")
        walker = TreeWalker(parsed)
        walker = ForgeHTMLSanitizerFilter(walker)  # this is our custom step
        s = html5lib.serializer.HTMLSerializer()
        return s.render(walker)


class AutolinkPattern(markdown.inlinepatterns.InlineProcessor):

    def handleMatch(self, m: re.Match[str], data: str) -> tuple[etree.Element | str | None, int | None, int | None]:
        old_link = m.group(1)
        result = etree.Element('a')
        result.text = old_link
        # since this is run before the builtin 'escape' processor, we have to
        # do our own unescaping
        for char in self.md.ESCAPED_CHARS:
            old_link = old_link.replace('\\' + char, char)
        result.set('href', old_link)
        return result, m.start(0), m.end(0)


class ForgeMacroIncludePreprocessor(markdown.preprocessors.Preprocessor):

    '''Join include statements to prevent extra <br>'s inserted by nl2br extension.

    Converts:
    [[include ref=some_ref]]
    [[include ref=some_other_ref]]

    To:
    [[include ref=some_ref]][[include ref=some_other_ref]]
    '''
    pattern = re.compile(r'^\s*\[\[include ref=[^\]]*\]\]\s*$', re.IGNORECASE)

    def run(self, lines):
        buf = []
        result = []
        for line in lines:
            if self.pattern.match(line):
                buf.append(line)
            else:
                if buf:
                    result.append(''.join(buf))
                    buf = []
                result.append(line)
        return result
