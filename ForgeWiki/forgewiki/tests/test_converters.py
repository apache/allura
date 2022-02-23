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


from unittest import skipIf

from alluratest.tools import module_not_available

from forgewiki import converters


@skipIf(module_not_available('mediawiki'), 'mediawiki required')
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


def test_convert_toc():
    '''Test that Table of Contents (TOC) converts properly'''
    wiki_html = """<div>Some html before toc</div>
<div id="toc">
    Table of Contents
    <ul>
        <li><a href="#h1">Some heading</a></li>
    </ul>
</div>
<div>Some html after toc</div>
"""
    expected_output = """<div>Some html before toc</div>
[TOC]
<div>Some html after toc</div>
"""
    output = converters._convert_toc(wiki_html)
    assert output == expected_output, output


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
