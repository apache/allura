import re
import logging
from urlparse import urljoin

from tg import config
from pylons import request
from BeautifulSoup import BeautifulSoup

import markdown
import feedparser

from . import macro
from . import helpers as h
from allura import model as M

log = logging.getLogger(__name__)

PLAINTEXT_BLOCK_RE = re.compile( \
    r'(?P<bplain>\[plain\])(?P<code>.*?)(?P<eplain>\[\/plain\])',
    re.MULTILINE|re.DOTALL
    )

MACRO_PATTERN = r'\[\[([^\]\[]+)\]\]'


class ForgeExtension(markdown.Extension):

    def __init__(self, wiki=False, email=False, macro_context=None):
        markdown.Extension.__init__(self)
        self._use_wiki = wiki
        self._is_email = email
        self._macro_context = macro_context

    def extendMarkdown(self, md, md_globals):
        md.registerExtension(self)
        md.preprocessors['fenced-code'] = FencedCodeProcessor()
        md.preprocessors.add('plain_text_block', PlainTextPreprocessor(md), "_begin")
        md.inlinePatterns['autolink_1'] = AutolinkPattern(r'(http(?:s?)://[a-zA-Z0-9./\-_0%?&=+#;~:]+)')
        # replace the link pattern with our extended version
        md.inlinePatterns['link'] = ForgeLinkPattern(markdown.inlinepatterns.LINK_RE, md, ext=self)
        md.inlinePatterns['short_reference'] = ForgeLinkPattern(markdown.inlinepatterns.SHORT_REF_RE, md, ext=self)
        # macro must be processed before links
        md.inlinePatterns.add('macro', ForgeMacroPattern(MACRO_PATTERN, md, ext=self), '<link')
        self.forge_link_tree_processor = ForgeLinkTreeProcessor(md)
        md.treeprocessors['links'] = self.forge_link_tree_processor
        # Sanitize HTML
        md.postprocessors['sanitize_html'] = HTMLSanitizer()
        # Rewrite all relative links that don't start with . to have a '../' prefix
        md.postprocessors['rewrite_relative_links'] = RelativeLinkRewriter(
            make_absolute=self._is_email)
        # Put a class around markdown content for custom css
        md.postprocessors['add_custom_class'] = AddCustomClass()
        md.postprocessors['mark_safe'] = MarkAsSafe()

    def reset(self):
        self.forge_link_tree_processor.reset()


class ForgeLinkPattern(markdown.inlinepatterns.LinkPattern):

    artifact_re = re.compile(r'((.*?):)?((.*?):)?(.+)')

    def __init__(self, *args, **kwargs):
        self.ext = kwargs.pop('ext')
        markdown.inlinepatterns.LinkPattern.__init__(self, *args, **kwargs)

    def handleMatch(self, m):
        el = markdown.util.etree.Element('a')
        el.text = m.group(2)
        is_link_with_brackets = False
        try:
            href = m.group(9)
        except IndexError:
            href = m.group(2)
            is_link_with_brackets = True
        try:
            title = m.group(13)
        except IndexError:
            title = None

        if href:
            if href == 'TOC':
                return '[TOC]'  # skip TOC
            if self.artifact_re.match(href):
                href, classes = self._expand_alink(href, is_link_with_brackets)
            el.set('href', self.sanitize_url(self.unescape(href.strip())))
            el.set('class', classes)
        else:
            el.set('href', '')

        if title:
            title = markdown.inlinepatterns.dequote(self.unescape(title))
            el.set('title', title)

        return el

    def _expand_alink(self, link, is_link_with_brackets):
        '''Return (href, classes) for an artifact link'''
        classes = ''
        if is_link_with_brackets:
            classes = 'alink'
        href = link
        shortlink = M.Shortlink.lookup(link)
        if shortlink:
            href = shortlink.url
            self.ext.forge_link_tree_processor.alinks.append(shortlink)
        elif self.ext._use_wiki and ':' not in link:
            href = h.urlquote(link)
            classes += ' notfound'
        return href, classes


class PlainTextPreprocessor(markdown.preprocessors.Preprocessor):
    '''
    This was used earlier for [plain] tags that the Blog tool's rss importer
    created, before html2text did good escaping of all special markdown chars.
    Can be deprecated.
    '''

    def run(self, lines):
        text = "\n".join(lines)
        while 1:
            res = PLAINTEXT_BLOCK_RE.finditer(text)
            for m in res:
                code = self._escape(m.group('code'))
                placeholder = self.markdown.htmlStash.store(code, safe=True)
                text = '%s%s%s'% (text[:m.start()], placeholder, text[m.end():])
                break
            else:
                break
        return text.split("\n")

    def _escape(self, txt):
        """ basic html escaping """
        txt = txt.replace('&', '&amp;')
        txt = txt.replace('<', '&lt;')
        txt = txt.replace('>', '&gt;')
        txt = txt.replace('"', '&quot;')
        return txt


class FencedCodeProcessor(markdown.preprocessors.Preprocessor):
    pattern = '~~~~'

    def run(self, lines):
        in_block = False
        new_lines = []
        for line in lines:
            if line.lstrip().startswith(self.pattern):
                in_block = not in_block
                continue
            if in_block:
                new_lines.append('    ' + line)
            else:
                new_lines.append(line)
        return new_lines


class ForgeMacroPattern(markdown.inlinepatterns.Pattern):

    def __init__(self, *args, **kwargs):
        self.ext = kwargs.pop('ext')
        self.macro = macro.parse(self.ext._macro_context)
        markdown.inlinepatterns.Pattern.__init__(self, *args, **kwargs)

    def handleMatch(self, m):
        html = self.macro(m.group(2))
        placeholder = self.markdown.htmlStash.store(html)
        return placeholder


class ForgeLinkTreeProcessor(markdown.treeprocessors.Treeprocessor):
    '''Wraps artifact links with []'''

    def __init__(self, parent):
        self.parent = parent
        self.alinks = []

    def run(self, root):
        for node in root.getiterator('a'):
            if 'alink' in node.get('class', '').split() and node.text:
                node.text = '[' + node.text + ']'
        return root

    def reset(self):
        self.alinks = []


class MarkAsSafe(markdown.postprocessors.Postprocessor):

    def run(self, text):
        return h.html.literal(text)


class AddCustomClass(markdown.postprocessors.Postprocessor):

    def run(self, text):
        return '<div class="markdown_content">%s</div>' % text


class RelativeLinkRewriter(markdown.postprocessors.Postprocessor):

    def __init__(self, make_absolute=False):
        self._make_absolute = make_absolute

    def run(self, text):
        try:
            if not request.path_info.endswith('/'): return text
        except:
            # Must be being called outside the request context
            pass
        soup = BeautifulSoup(text)
        if self._make_absolute:
            rewrite = self._rewrite_abs
        else:
            rewrite = self._rewrite
        for link in soup.findAll('a'):
            rewrite(link, 'href')
        for link in soup.findAll('img'):
            rewrite(link, 'src')
        return unicode(soup)

    def _rewrite(self, tag, attr):
        val = tag.get(attr)
        if val is None: return
        if ' ' in val:
            # Don't urllib.quote to avoid possible double-quoting
            # just make sure no spaces
            val = val.replace(' ', '%20')
            tag[attr] = val
        if '://' in val:
            if 'sf.net' in val or 'sourceforge.net' in val:
                return
            else:
                tag['rel']='nofollow'
                return
        if val.startswith('/'): return
        if val.startswith('.'): return
        if val.startswith('mailto:'): return
        if val.startswith('#'): return
        tag[attr] = '../' + val

    def _rewrite_abs(self, tag, attr):
        self._rewrite(tag, attr)
        val = tag.get(attr)
        val = urljoin(config.get('base_url', 'http://sourceforge.net/'),val)
        tag[attr] = val


class HTMLSanitizer(markdown.postprocessors.Postprocessor):

    def run(self, text):
        try:
            p = feedparser._HTMLSanitizer('utf-8')
        except TypeError: # $@%## pre-released versions from SOG
            p = feedparser._HTMLSanitizer('utf-8', '')
        p.feed(text.encode('utf-8'))
        return unicode(p.output(), 'utf-8')


class AutolinkPattern(markdown.inlinepatterns.LinkPattern):

    def handleMatch(self, mo):
        old_link = mo.group(2)
        result = markdown.util.etree.Element('a')
        result.text = old_link
        result.set('href', old_link)
        return result
