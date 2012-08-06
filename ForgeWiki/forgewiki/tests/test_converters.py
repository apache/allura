from nose.tools import assert_equal
from IPython.testing.decorators import module_not_available, skipif

from alluratest.controller import setup_basic_test, setup_global_objects
from forgewiki import converters

@skipif(module_not_available('mediawiki'))
def test_mediawiki2markdown():
    mediawiki_text = """
'''bold''' ''italics''
== Getting started ==
* [http://www.mediawiki.org/wiki/Manual:Configuration_settings Configuration]
* [http://www.mediawiki.org/wiki/Manual:FAQ MediaWiki FAQ]
    """
    mediawiki_output = converters.mediawiki2markdown(mediawiki_text)
    assert "**bold** _italics_" in mediawiki_output
    assert "## Getting started" in mediawiki_output
    assert ("* [MediaWiki FAQ](http://www.mediawiki.org/wiki/Manual:FAQ)"
            in mediawiki_output)


def test_mediawiki_internal_links2markdown():
    text = """Example page!
Inline image: [[File:image.png]]
Link to file: [[Media:attach.pdf|Att]]
File: [[Media:attach.pdf]]
Inline image in old format: [[Image:image.png]]
"""
    output = converters.mediawiki_internal_links2markdown(text, 'Example page')
    assert 'Example page!' in output
    assert 'Inline image: [[img src=image.png]]' in output
    assert 'Link to file: [Att](Example page/attachment/attach.pdf)' in output
    assert 'File: [attach.pdf](Example page/attachment/attach.pdf)' in output
    assert 'Inline image in old format: [[img src=image.png]]' in output
