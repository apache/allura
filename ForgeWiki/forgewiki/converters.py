#-*- python -*-
import html2text
import bbcode
# https://github.com/zikzakmedia/python-mediawiki.git
from mediawiki import wiki2html

html2text.BODY_WIDTH = 0


def mediawiki2markdown(source):
    p = bbcode.Parser(newline='\n', escape_html=False, replace_links=False,
        replace_cosmetic=False)
    cleanbb_text = p.format(source)
    wiki_content = wiki2html(cleanbb_text, True)
    markdown_text = html2text.html2text(wiki_content)
    return markdown_text
