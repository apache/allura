#-*- python -*-
import logging
import json

log = logging.getLogger(__name__)

class ImportException(Exception):
    pass

class ImportSupport(object):
    def __init__(self):
        self.warnings = []
        self.errors = []
        self.options = {}

    def init_options(self, options_json):
        self.options = json.loads(options_json)
        opt_keywords = self.option('keywords_as', 'split_labels')
        if opt_keywords == 'single_label':
            self.FIELD_MAP['keywords'] = ('labels', lambda s: [s])
        elif opt_keywords == 'custom':
            del self.FIELD_MAP['keywords']

    def option(self, name, default=None):
        return self.options.get(name, False)

    def perform_import(self, doc, options):
        log.info('import called: %s', options)
        self.init_options(options)
        return {'status': True, 'errors': self.errors, 'warnings': self.warnings}

if __name__ == "__main__":
    mediawiki_text = """
<b>LALALALA</b>
[b]bolded text[/b]
[i]italicized text[/i]
[u]underlined text[/u]
[s]strikethrough text[/s]
[code]monospaced text[/code]
[table] [tr] [td]table data[/td] [/tr] [/table]
[list] [*]Entry 1 [*]Entry 2 [/list]

<big>'''MediaWiki has been successfully installed.'''</big>

Consult the [http://meta.wikimedia.org/wiki/Help:Contents User's Guide] for information on using the wiki software.

== Getting started ==
* [http://www.mediawiki.org/wiki/Manual:Configuration_settings Configuration settings list]
* [http://www.mediawiki.org/wiki/Manual:FAQ MediaWiki FAQ]
* [http://lists.wikimedia.org/mailman/listinfo/mediawiki-announce MediaWiki release mailing list]

This is a sample attachment:

[[Image:MediaWikiSidebarLogo.png]]
"""
    im = ImportSupport()
    #print im.perform_import(mediawiki_text, '{"opt": 1}')

    import bbcode
    p = bbcode.Parser(newline='\n', escape_html=False, replace_links=False, replace_cosmetic=False)
    cleanbb_text = p.format(mediawiki_text)

    #print cleanbb_text

    from mwlib import parser, expander, uparser
    parse = uparser.simpleparse
    r = parse(cleanbb_text)
    sections = [x.children[0].asText().strip() for x in r.children if isinstance(x, parser.Section)]
    #print dir(r)
    #print r

    from mwlib import advtree
    import mwlib.parser
    import sys
    from mwlib.odfwriter import ODFWriter, preprocess

    advtree.buildAdvancedTree(r)
    preprocess(r)

    print "SHOW->"
    mwlib.parser.show(sys.stdout, r)
