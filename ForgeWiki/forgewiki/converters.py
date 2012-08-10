#-*- python -*-
import html2text
import re

html2text.BODY_WIDTH = 0

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
        return r'[%s](%s)' % (match.group(2), page_name)
    return r'[%s]' % page_name


def mediawiki2markdown(source):
    try:
        from mediawiki import wiki2html
    except ImportError:
        raise ImportError('GPL library "mediawiki" from https://github.com/zikzakmedia/python-mediawiki.git '
                                 'is required for this operation')

    wiki_content = wiki2html(source, True)
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
