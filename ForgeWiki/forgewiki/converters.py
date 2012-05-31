#-*- python -*-
import html2text
# https://github.com/zikzakmedia/python-mediawiki.git
from mediawiki import wiki2html

html2text.BODY_WIDTH = 0


def mediawiki2markdown(source):
    wiki_content = wiki2html(source, True)
    markdown_text = html2text.html2text(wiki_content)
    return markdown_text
