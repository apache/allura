#-*- python -*-
import html2text
import bbcode
# https://github.com/zikzakmedia/python-mediawiki.git
from mediawiki import *

class ImportSupport(object):
    @staticmethod
    def mediawiki2markdown(source):
        p = bbcode.Parser(newline='\n', escape_html=False, replace_links=False, replace_cosmetic=False)
        cleanbb_text = p.format(mediawiki_text)
        wiki_content = wiki2html(cleanbb_text, True)
        markdown_text = html2text.html2text(wiki_content)
        return markdown_text

if __name__ == "__main__":
    mediawiki_text = """[b]bolded text[/b][i]italicized text[/i]

== Getting started ==
* [http://www.mediawiki.org/wiki/Manual:Configuration_settings Configuration settings list]
* [http://www.mediawiki.org/wiki/Manual:FAQ MediaWiki FAQ]
* [http://lists.wikimedia.org/mailman/listinfo/mediawiki-announce MediaWiki release mailing list]

This is a sample attachment:

[[Image:MediaWikiSidebarLogo.png]]
"""
    print ImportSupport.mediawiki2markdown(mediawiki_text)
