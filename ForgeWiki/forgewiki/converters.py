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

import re
from bs4 import BeautifulSoup
import six

_inline_img = re.compile(r'\[\[(File|Image):([^\]|]+)[^]]*\]\]', re.UNICODE)
_inline_img_markdown = r'[[img src=\2]]'
_link_to_attach = re.compile(r'\[\[Media:([^\]|]+)\|?([^]]*)\]\]', re.UNICODE)
_internal_link = re.compile(r'\[\[([^\]|]+)\|?([^]]*)\]\]', re.UNICODE)


def _link_to_attach_markdown(page_title):
    pattern = r'[%s](%s/attachment/%s)'

    def replacement(match):
        if match.group(2):
            return pattern % (match.group(2), page_title, match.group(1))
        return pattern % (match.group(1), page_title, match.group(1))

    return replacement


def _internal_link_markdown(match):
    page_name = match.group(1)
    attachments = ('File:', 'Image:', 'Media:')
    if page_name.startswith(attachments):
        return match.group(0)  # skip attachments links
    page_name = page_name.replace(' ', '_')
    page_name = page_name[:1].upper() + page_name[1:]
    if match.group(2):
        return fr'[{match.group(2)}]({page_name})'
    return r'[%s]' % page_name


def _convert_toc(wiki_html):
    """Convert Table of Contents from mediawiki to markdown"""
    soup = BeautifulSoup(wiki_html, 'html.parser')
    for toc_div in soup.findAll('div', id='toc'):
        toc_div.replaceWith('[TOC]')
    return str(soup)


def mediawiki2markdown(source):
    try:
        import html2text
        from mediawiki import wiki2html
    except ImportError:
        raise ImportError("""This operation requires GPL libraries:
        "mediawiki" (https://pypi.org/project/mediawiki2html/)
        "html2text" (https://pypi.org/project/html2text/)""")

    html2text.BODY_WIDTH = 0

    wiki_content = wiki2html(source, True)
    wiki_content = _convert_toc(wiki_content)
    markdown_text = html2text.html2text(wiki_content)
    markdown_text = markdown_text.replace('<', '&lt;').replace('>', '&gt;')
    return markdown_text


def mediawiki_internal_links2markdown(markdown_text, page_title):
    """Convert MediaWiki internal links to attachments to ForgeWiki format.

    args:
    markdown_text - text, converted by mediawiki2markdown convertor.
    page_title - title of ForgeWiki page.
                 Used for constructing proper links to attachments.
    """
    output = _internal_link.sub(_internal_link_markdown, markdown_text)
    output = _inline_img.sub(_inline_img_markdown, output)
    output = _link_to_attach.sub(_link_to_attach_markdown(page_title), output)
    return output
