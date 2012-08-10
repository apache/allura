from IPython.testing.decorators import module_not_available, skipif

from forgewiki import converters


@skipif(module_not_available('mediawiki'))
def test_mediawiki2markdown():
    mediawiki_text = """
'''bold''' ''italics''
== Getting started ==
* [http://www.mediawiki.org/wiki/Manual:Configuration_settings Configuration]
* [http://www.mediawiki.org/wiki/Manual:FAQ MediaWiki FAQ]
<plugin>.plugin()
    """
    mediawiki_output = converters.mediawiki2markdown(mediawiki_text)
    assert "**bold** _italics_" in mediawiki_output
    assert "## Getting started" in mediawiki_output
    assert ("* [MediaWiki FAQ](http://www.mediawiki.org/wiki/Manual:FAQ)"
            in mediawiki_output)
    assert '&lt;plugin&gt;.plugin()' in mediawiki_output


def test_mediawiki_internal_links2markdown():
    text = """Example page!
Inline image: [[File:image.png]]
Link to file: [[Media:attach.pdf|Att]]
File: [[Media:attach.pdf]]
Inline image in old format: [[Image:image.png]]
Internal link1: [[Some Page]]
Internal link2: [[SomePage|link text]]
Internal link3: [[ircdb#ircdb.checkCapability()|ircdb.checkCapability()]]
"""
    output = converters.mediawiki_internal_links2markdown(text, 'Example page')
    assert 'Example page!' in output
    assert 'Inline image: [[img src=image.png]]' in output
    assert 'Link to file: [Att](Example page/attachment/attach.pdf)' in output
    assert 'File: [attach.pdf](Example page/attachment/attach.pdf)' in output
    assert 'Inline image in old format: [[img src=image.png]]' in output
    assert 'Internal link1: [Some_Page]' in output, output
    assert 'Internal link2: [link text](SomePage)' in output, output
    assert ('Internal link3: [ircdb.checkCapability()]'
            '(Ircdb#ircdb.checkCapability())') in output, output
