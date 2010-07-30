import re
import os
import logging
import string
from collections import defaultdict
from urllib import quote
from ConfigParser import RawConfigParser
from pprint import pformat

from tg import config
from pylons import c, g, request
from BeautifulSoup import BeautifulSoup

import oembed
import markdown
import feedparser

from . import macro

log = logging.getLogger(__name__)

class ForgeExtension(markdown.Extension):

    def __init__(self, wiki=False):
        markdown.Extension.__init__(self)
        self._use_wiki = wiki

    def extendMarkdown(self, md, md_globals):
        md.registerExtension(self)
        self.forge_processor = ForgeProcessor(self._use_wiki, md)
        self.forge_processor.install()
        md.inlinePatterns['autolink_1'] = AutolinkPattern(r'(http(?:s?)://[a-zA-Z0-9./\-_0%?&=+]+)')
        md.treeprocessors['br'] = LineOrientedTreeProcessor(md)
        # Sanitize HTML
        md.postprocessors['sanitize_html'] = HTMLSanitizer()
        # Rewrite all relative links that don't start with . to have a '../' prefix
        md.postprocessors['rewrite_relative_links'] = RelativeLinkRewriter()

    def reset(self):
        self.forge_processor.reset()

class ForgeProcessor(object):
    alink_pattern = r'(?<!\[)\[([^\]\[]*)\]'
    macro_pattern = r'\[(\[([^\]\[]*)\])\]'
    placeholder_prefix = '\x02jgimwge'
    placeholder = '%s:%%s:%%.4d\x03' % placeholder_prefix
    placeholder_re = re.compile('%s:(\\w+):(\\d+)\x03' % placeholder_prefix)

    def __init__(self, use_wiki = False, markdown=None):
        self.markdown = markdown
        self._use_wiki = use_wiki
        self.inline_patterns = {
            'forge.alink' : ForgeInlinePattern(self, self.alink_pattern),
            'forge.macro' : ForgeInlinePattern(self, self.macro_pattern)}
        self.postprocessor = ForgePostprocessor(self)
        self.tree_processor = ForgeTreeProcessor(self)
        self.reset()
        self.artifact_re = re.compile(r'((.*?):)?((.*?):)?(.+)')
        self.macro_re = re.compile(self.alink_pattern)
        self.oembed_re = re.compile('embed#(.*)')

    def install(self):
        for k,v in self.inline_patterns.iteritems():
            self.markdown.inlinePatterns[k] = v
        if self._use_wiki:
            self.markdown.treeprocessors['forge'] = self.tree_processor
        self.markdown.postprocessors['forge'] = self.postprocessor

    def store(self, raw):
        if self.macro_re.match(raw):
            stash = 'macro'
            raw = raw[1:-1] # strip off the enclosing []
        elif self.oembed_re.match(raw): stash = 'oembed'
        elif self.artifact_re.match(raw): stash = 'artifact'
        else: return raw
        return self._store(stash, raw)

    def _store(self, stash_name, value):
        placeholder = self.placeholder % (stash_name, len(self.stash[stash_name]))
        self.stash[stash_name].append(value)
        return placeholder

    def lookup(self, stash, id):
        stash = self.stash.get(stash, [])
        if id >= len(stash): return ''
        return stash[id]

    def compile(self):
        from pyforge import model as M
        if self.stash['artifact'] or self.stash['link']:
            try:
                self.alinks = M.ArtifactLink.lookup_links(self.stash['artifact'])
                self.alinks.update(M.ArtifactLink.lookup_links(self.stash['link']))
            except:
                self.alinks = {}
        self.stash['artifact'] = map(self._expand_alink, self.stash['artifact'])
        self.stash['link'] = map(self._expand_link, self.stash['link'])
        self.stash['macro'] = map(macro.parse, self.stash['macro'])
        self.stash['oembed'] = map(self._expand_oembed, self.stash['oembed'])

    def reset(self):
        self.stash = dict(
            artifact=[],
            macro=[],
            oembed=[],
            link=[])
        self.alinks = {}
        self.compiled = False

    def _expand_alink(self, link):
        new_link = self.alinks.get(link, None)
        if new_link:
            return '<a href="%s">[%s]</a>' % (
                new_link.url, link)
        elif self._use_wiki and ':' not in link:
            return '<a href="%s" class="notfound">[%s]</a>' % (
                link, link)
        else:
            return link

    def _expand_link(self, link):
        reference = self.alinks[link]
        if not reference:
            return 'notfound'
        else:
            return ''

    def _expand_oembed(self, link):
        href = link.split('#', 1)[-1]
        try:
            if href.startswith('('):
                size, href = href.split(')')
                size = size[1:]
                width,height = size.split(',')
            else:
                width = height = None
            response = g.oembed_consumer.embed(href)
            data = response.getData()
            log.info('Got response:\n%s', pformat(data))
            if width is None: width = data.get('width', '100%')
            if height is None: height = data.get('height', '300')
            return self._render_iframe(href, width, height)
        except oembed.OEmbedNoEndpoint:
            result = '<a href="%s">(cannot be embedded - no endpoint)' % href
            return result
        except Exception, ve:
            result = '<a href="%s">(cannot be embedded (%s))' % (href, ve)
            return result

    def _render_iframe(self, href, width, height):
        return ('<iframe src=http://%s?href=%s" '
                'width="%s" '
                'height="%s">OEMBED</iframe>' % (
                config['oembed.host'], quote(href),
                width,
                height))

class ForgeInlinePattern(markdown.inlinepatterns.Pattern):

    def __init__(self, parent, pattern):
        self.parent = parent
        markdown.inlinepatterns.Pattern.__init__(
            self, pattern, parent.markdown)

    def handleMatch(self, m):
        return self.parent.store(m.group(2))

class ForgePostprocessor(markdown.postprocessors.Postprocessor):

    def __init__(self, parent):
        self.parent = parent
        markdown.postprocessors.Postprocessor.__init__(
            self, parent.markdown)

    def run(self, text):
        self.parent.compile()
        def repl(mo):
            return self.parent.lookup(mo.group(1), int(mo.group(2)))
        return self.parent.placeholder_re.sub(repl, text)

class ForgeTreeProcessor(markdown.treeprocessors.Treeprocessor):
    '''This flags intra-wiki links that point to non-existent pages'''

    def __init__(self, parent):
        self.parent = parent

    def run(self, root):
        for node in root.getiterator('a'):
            href = node.get('href')
            if not href: continue
            if '/' in href: continue
            classes = node.get('class', '').split() + [ self.parent._store('link', href) ]
            node.attrib['class'] = ' '.join(classes)
        return root

class RelativeLinkRewriter(markdown.postprocessors.Postprocessor):

    def run(self, text):
        try:
            if not request.path_info.endswith('/'): return text
        except:
            # Must be being called outside the request context
            pass
        soup = BeautifulSoup(text)
        def rewrite(tag, attr):
            val = tag.get(attr)
            if val is None: return
            if '://' in val: return
            if val.startswith('/'): return
            if val.startswith('.'): return
            tag[attr] = '../' + val
        for link in soup.findAll('a'):
            rewrite(link, 'href')
        for link in soup.findAll('img'):
            rewrite(link, 'src')
        return unicode(soup)

class HTMLSanitizer(markdown.postprocessors.Postprocessor):

    def run(self, text):
        try:
            p = feedparser._HTMLSanitizer('utf-8')
        except TypeError: # $@%## pre-released versions from SOG
            p = feedparser._HTMLSanitizer('utf-8', '')
        p.feed(text.encode('utf-8'))
        return unicode(p.output(), 'utf-8')

class LineOrientedTreeProcessor(markdown.treeprocessors.Treeprocessor):
    '''Once MD is satisfied with the etree, this runs to replace \n with <br/>
    within <p>s.
    '''

    def __init__(self, md):
        self._markdown = md
    
    def run(self, root):
        for node in root.getiterator('p'):
            if not node.text: continue
            if '\n' not in node.text: continue
            text = self._markdown.serializer(node)
            text = self._markdown.postprocessors['raw_html'].run(text)
            text = text.strip()
            if '\n' not in text: continue
            new_text = (text
                        .replace('<br>', '<br/>')
                        .replace('\n', '<br/>'))
            try:
                new_node = markdown.etree.fromstring(new_text)
                node.clear()
                node.text = new_node.text
                node[:] = list(new_node)
            except SyntaxError:
                log.exception('Error adding <br> tags: new text is %s', new_text)
                pass
        return root

class AutolinkPattern(markdown.inlinepatterns.LinkPattern):

    def handleMatch(self, mo):
        old_link = mo.group(2)
        result = markdown.etree.Element('a')
        result.text = old_link
        result.set('href', old_link)
        return result

