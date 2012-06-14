#-*- python -*-
import html2text
import re
# https://github.com/zikzakmedia/python-mediawiki.git
from mediawiki import wiki2html

html2text.BODY_WIDTH = 0

_inline_img = re.compile(r'\[\[(File|Image):([^\]|]+).*\]\]', re.UNICODE)
_inline_img_markdown = r'[[img src=\2]]'
_link_to_attach = re.compile(r'\[\[Media:([^\]|]+)\|?(.*)\]\]', re.UNICODE)


def _link_to_attach_markdown(page_title):
    pattern = r'[%s](%s/attachment/%s)'

    def replacement(match):
        if match.group(2):
            return pattern % (match.group(2), page_title, match.group(1))
        return pattern % (match.group(1), page_title, match.group(1))

    return replacement


def mediawiki2markdown(source):
    wiki_content = wiki2html(source, True)
    markdown_text = html2text.html2text(wiki_content)
    return markdown_text


def mediawiki_internal_links2markdown(markdown_text, page_title):
    """Convert MediaWiki internal links to attachments to ForgeWiki format.

    args:
    markdown_text - text, converted by mediawiki2markdown convertor.
    page_title - title of ForgeWiki page.
                 Used for constructing proper links to attachments.
    """
    output = _inline_img.sub(_inline_img_markdown, markdown_text)
    output = _link_to_attach.sub(_link_to_attach_markdown(page_title), output)
    return output
