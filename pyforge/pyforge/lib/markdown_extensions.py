import re
import logging
import string
from urllib import quote
from ConfigParser import RawConfigParser
from pprint import pformat

from tg import config
from pylons import g

import oembed
import markdown

log = logging.getLogger(__name__)

class ForgeExtension(markdown.Extension):
    core_artifact_link = r'(\[((?P<project_id>.*?):)?((?P<app_id>.*?):)?(?P<artifact_id>.*?)\])'

    def __init__(self, wiki=False):
        markdown.Extension.__init__(self)
        self._use_wiki = wiki

    def extendMarkdown(self, md, md_globals):
        md.treeprocessors['br'] = LineOrientedTreeProcessor()
        md.inlinePatterns['oembed'] = OEmbedPattern(r'\[embed#(.*?)\]')
        md.inlinePatterns['autolink_1'] = AutolinkPattern(r'(http(?:s?)://\S*)')
        md.inlinePatterns['artifact_1'] = ArtifactLinkPattern('^' + self.core_artifact_link)
        md.inlinePatterns['artifact_2'] = ArtifactLinkPattern(r'\w' + self.core_artifact_link)
        if self._use_wiki:
            md.inlinePatterns['wiki'] = WikiLinkPattern(r'\b([A-Z]\w+[A-Z]+\w+)')

class LineOrientedTreeProcessor(markdown.treeprocessors.Treeprocessor):
    '''Once MD is satisfied with the etree, this runs to replace \n with <br/>
    within <p>s.
    '''
    def run(self, root):
        for node in root.getiterator('p'):
            if node.text is None: continue
            parts = node.text.split('\n')
            if len(parts) == 1: continue
            node.text = parts[0]
            for p in parts[1:]:
                br = markdown.etree.Element('br')
                br.tail = p
                node.append(br)
        return root

class ArtifactLinkPattern(markdown.inlinepatterns.LinkPattern):

    def handleMatch(self, mo):
        from pyforge import model as M
        old_link = mo.group(2)
        new_link = M.ArtifactLink.lookup(old_link)
        if new_link:
            result = markdown.etree.Element('a')
            result.text = mo.group(2)
            result.set('href', new_link.url)
            return result
        else:
            return old_link

class AutolinkPattern(markdown.inlinepatterns.LinkPattern):

    def handleMatch(self, mo):
        old_link = mo.group(2)
        result = markdown.etree.Element('a')
        result.text = old_link
        result.set('href', old_link)
        return result

class WikiLinkPattern(markdown.inlinepatterns.LinkPattern):

    def handleMatch(self, mo):
        old_link = mo.group(2)
        result = markdown.etree.Element('a')
        result.text = old_link
        result.set('href', '../' + old_link + '/')
        return result

class OEmbedPattern(markdown.inlinepatterns.LinkPattern):

    def handleMatch(self, mo):
        href = mo.group(2)
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
            result = markdown.etree.Element('a')
            result.text = href + ' (cannot be embedded - no endpoint)'
            result.set('href', href)
            return result
        except Exception, ve:
            result = markdown.etree.Element('a')
            result.text = href + ' (cannot be embedded (%s)' % ve
            result.set('href', href)
            return result

    def _render_iframe(self, href, width, height):
        iframe = markdown.etree.Element('iframe')
        href = 'http://%s?href=%s' % (
            config['oembed.host'], quote(href))
        iframe.set('src', href)
        iframe.set('width', str(width))
        iframe.set('height', str(height))
        return iframe

