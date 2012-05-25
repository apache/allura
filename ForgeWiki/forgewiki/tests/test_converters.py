from pylons import c, g

from nose.tools import assert_equal

from alluratest.controller import setup_basic_test, setup_global_objects
from allura.tests import decorators as td
from forgewiki import converters

def setUp():
    setup_basic_test()
    setup_with_tools()

@td.with_wiki
def setup_with_tools():
    setup_global_objects()
    g.set_app('wiki')

def test_mediawiki2markdown():
    bbcode_text = "[b]bolded text[/b][i]italicized text[/i]"
    bbcode_output = converters.mediawiki2markdown(bbcode_text)
    assert "**bolded text**_italicized text_" in bbcode_output

    mediawiki_text = """
== Getting started ==
* [http://www.mediawiki.org/wiki/Manual:Configuration_settings Configuration settings list]
* [http://www.mediawiki.org/wiki/Manual:FAQ MediaWiki FAQ]
    """
    mediawiki_output = converters.mediawiki2markdown(mediawiki_text)
    assert "## Getting started" in mediawiki_output
    assert "* [MediaWiki FAQ](http://www.mediawiki.org/wiki/Manual:FAQ)" in mediawiki_output
