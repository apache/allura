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

"""
Mutation-XSS style checks for HTML sanitizing.  Each payload is sanitized, then parsed again the way a
browser would, and the resulting tree must have nothing script-capable in it.  The checks don't depend
on how the sanitizer is implemented.
"""
import itertools
import re

import html5lib
import pytest
from tg import app_globals as g

from alluratest.controller import setup_basic_test, setup_global_objects, setup_unit_test
from allura.lib import helpers as h
from allura.tests import decorators as td

SVG = html5lib.constants.namespaces['svg']

SINKS = [
    '<img src=x onerror=alert(1)>',
    '</style><img src=x onerror=alert(1)>',
    '<!--</style><img src=x onerror=alert(1)>-->',
    '<style><img src=x onerror=alert(1)></style>',
    '<style><!--</style><img src=x onerror=alert(1)>--></style>',
    '<img title="</style><img src=x onerror=alert(1)>">',
    '<a href="javascript:alert(1)">x</a>',
    '<iframe src="https://www.youtube.com/embed/x"><img src=x onerror=alert(1)></iframe>',
    '<iframe src="https://www.youtube.com/embed/x"></iframe><img src=x onerror=alert(1)>',
    '<script>alert(1)</script>',
    '<xmp><img src=x onerror=alert(1)></xmp>',
    '<noscript><p title="</noscript><img src=x onerror=alert(1)>"></noscript>',
    '<p title="</noscript><img src=x onerror=alert(1)>">',
    '<textarea></textarea><img src=x onerror=alert(1)>',
    '<title><img src=x onerror=alert(1)></title>',
    '<plaintext><img src=x onerror=alert(1)>',
    '<![CDATA[<img src=x onerror=alert(1)>]]>',
    '<?xml <img src=x onerror=alert(1)>?>',
    '<!--><img src=x onerror=alert(1)>-->',
    '<!----!><img src=x onerror=alert(1)>-->',
    '<a title="&lt;img src=x onerror=alert(1)&gt;">x</a>',
    '<a href="java&#x09;script:alert(1)">x</a>',
    '<a href="&#0;javascript:alert(1)">x</a>',
    '<a href="jav\x00ascript:alert(1)">x</a>',
    '<a href=" \x01javascript:alert(1)">x</a>',
    '<a href="javascript&colon;alert(1)">x</a>',
    '<a href="JaVaScRiPt:alert(1)">x</a>',
    '<a href="vbscript:x">x</a>',
    '<a href="data:text/html,<script>alert(1)</script>">x</a>',
    '<a href="data:image/png;text/html,x">x</a>',
    '<img src="data:image/svg+xml,<svg onload=alert(1)>">',
    '<img srcset="javascript:alert(1) 1x, data:text/html,x 2x">',
    '<math href="javascript:alert(1)">x</math>',
    '<math xlink:href="javascript:alert(1)">x</math>',
    '<math><maction actiontype="statusline" xlink:href="javascript:alert(1)">x</maction></math>',
    '<input type=checkbox onclick=alert(1) name=x form=f formaction="javascript:alert(1)">',
    '<input type="checkbox" type="image" src=x onerror=alert(1)>',
    '<input type="CHECKBOX">',
    '<details open ontoggle=alert(1)><summary>x</summary></details>',
    '<template><img src=x onerror=alert(1)></template>',
    '<object data="javascript:alert(1)"></object><embed src="javascript:alert(1)">',
    '<base href="javascript:/">',
    '<meta http-equiv=refresh content="0;url=javascript:alert(1)">',
    '<link rel=stylesheet href=//evil>',
    '<area href="javascript:alert(1)"><map name=x><area href="javascript:alert(1)"></map>',
    '<video poster="javascript:alert(1)"><source src="javascript:alert(1)"></video>',
    '<table background="javascript:alert(1)"><tr><td>x</td></tr></table>',
    '<button formaction="javascript:alert(1)">x</button>',
    '<p style="background:url(javascript:alert(1))">x</p>',
    '<p style="color:red;background-image:url(//evil/x)">x</p>',
    '<p style="color: expression(alert(1))">x</p>',
    '<p style="-moz-binding:url(//evil)">x</p>',
    '<p style="width:\\75rl(x)">x</p>',
    '<p style="position:fixed;top:0">x</p>',
    '<p style="--x:url(//evil)">x</p>',
    '<iframe src="https://www.youtube.com/embed/../../redirect?q=//evil"></iframe>',
    '<iframe src="https://www.youtube.com/embed/x" srcdoc="<script>alert(1)</script>"></iframe>',
    '<iframe src="https://www.youtube.com/embed/x" name="x" sandbox></iframe>',
    '<iframe src="https://www.youtube.com/embed/x"/><img src=x onerror=alert(1)>',
    '<iframe src="https://www.youtube.com/embed/x">&lt;/iframe&gt;&lt;img src=x onerror=alert(1)&gt;</iframe>',
    '<img name=cookie id=x><form name=f><img name=getElementById>',
    '<a id="h-x" name="x">a</a><a id="fn:x">b</a>',
    '\x00<img src=x onerror=alert(1)>',
    '<sty\x00le><img src=x onerror=alert(1)></style>',
    '<a href="https://example.com/`onmouseover=alert(1)`">x</a>',
    '<a title="a\nb`c&quot;d\'e<f>g">x</a>',
]

WRAPPERS = [
    ('', ''),
    ('<math>', '</math>'),
    ('<math><mtext>', '</mtext></math>'),
    ('<math><mi>', '</mi></math>'),
    ('<math><mo>', '</mo></math>'),
    ('<math><mn>', '</mn></math>'),
    ('<math><ms>', '</ms></math>'),
    ('<math><annotation-xml>', '</annotation-xml></math>'),
    ('<math><annotation-xml encoding="text/html">', '</annotation-xml></math>'),
    ('<math><semantics><annotation-xml encoding="application/xhtml+xml">', '</annotation-xml></semantics></math>'),
    ('<math><mtext><table><mglyph>', '</mglyph></table></mtext></math>'),
    ('<math><mtext><table><malignmark>', '</malignmark></table></mtext></math>'),
    ('<math><mtext><mglyph><svg><mtext>', '</mtext></svg></mglyph></mtext></math>'),
    ('<math><mi><mglyph><svg><mtext><textarea><path id="</textarea>', '"></path></textarea></mtext></svg></mglyph></mi></math>'),
    ('<svg>', '</svg>'),
    ('<svg><foreignObject>', '</foreignObject></svg>'),
    ('<svg><desc>', '</desc></svg>'),
    ('<svg><title>', '</title></svg>'),
    ('<svg></p>', '</svg>'),
    ('<svg><p>', '</p></svg>'),
    ('<table>', '</table>'),
    ('<table><tr><td>', '</td></tr></table>'),
    ('<table><caption>', '</caption></table>'),
    ('<select>', '</select>'),
    ('<select><option>', '</option></select>'),
    ('<select><template>', '</template></select>'),
    ('<template>', '</template>'),
    ('<form>', '</form>'),
    ('<form><math><mtext></form><form><mglyph><style></math>', ''),
    ('<form><math><mtext></form><form><mglyph><svg><mtext><style><path id="</style>', '">'),
    ('<a href="#">', '</a>'),
    ('<a><p>', '</p></a>'),
    ('<p>', '</p>'),
    ('<noscript>', '</noscript>'),
    ('<noembed>', '</noembed>'),
    ('<noframes>', '</noframes>'),
    ('<xmp>', '</xmp>'),
    ('<textarea>', '</textarea>'),
    ('<title>', '</title>'),
    ('<style>', '</style>'),
    ('<object>', '</object>'),
    ('<iframe src="https://www.youtube.com/embed/x">', '</iframe>'),
    ('<math><mtext><iframe src="https://www.youtube.com/embed/x">', '</iframe></mtext></math>'),
    ('<math><ms><iframe src="https://www.youtube.com/embed/x">', '</iframe></ms></math>'),
    ('<math><mi><iframe src="https://www.youtube.com/embed/x">', '</iframe></mi></math>'),
    ('<!--', '-->'),
    ('<![CDATA[', ']]>'),
    ('<math><![CDATA[', ']]></math>'),
    ('<math><mtext><![CDATA[', ']]></mtext></math>'),
    ('<div title="', '">'),
    ('<details><summary>', '</summary></details>'),
    ('</div>', '<div>'),
    ('</div></div></body>', '<div><div>'),
    ('<frameset>', '</frameset>'),
    ('<body>', '</body>'),
    ('<html>', '</html>'),
    ('<head>', '</head>'),
]

INNER = ['', '<math>', '<math><mtext>', '<math><ms>', '<svg>', '<table>', '<select>', '<template>', '<form>',
         '<a>', '<p>', '<li>', '<dd>', '<mglyph>', '<malignmark>', '<annotation-xml encoding="text/html">']


def build_corpus() -> list[str]:
    corpus = []
    for (pre, post), sink in itertools.product(WRAPPERS, SINKS):
        corpus.append(pre + sink + post)
    for (pre, post), inner, sink in itertools.product(WRAPPERS, INNER, SINKS[:12]):
        corpus.append(pre + inner + sink + post)
    for (p1, s1), (p2, s2) in itertools.product(WRAPPERS[:30], WRAPPERS[:30]):
        corpus.append(p1 + p2 + SINKS[0] + SINKS[2] + s2 + s1)
    return list(dict.fromkeys(corpus))


FORBIDDEN_ELEMENTS = {
    'script', 'style', 'object', 'embed', 'applet', 'base', 'meta', 'link', 'frame', 'frameset', 'template',
    'form', 'button', 'select', 'option', 'textarea', 'noscript', 'noembed', 'noframes', 'xmp', 'plaintext', 'title',
}
# srcset is left out: images don't run javascript: or data: documents
URL_ATTRS = {'href', 'src', 'action', 'formaction', 'background', 'poster', 'data', 'lowsrc', 'dynsrc',
             'cite', 'longdesc', 'ping', 'xlink:href', 'base'}


def bad_url(val: str) -> bool:
    v = re.sub(r'[\x00-\x20\x7f-\xa0\s`]+', '', val).lower()
    return any(s in v for s in ('javascript:', 'vbscript:', 'data:text', 'data:image/svg', 'data:application'))


def split_ns(tag: str) -> tuple[str | None, str]:
    m = re.match(r'\{(.*)\}(.*)', tag)
    return m.groups() if m else (None, tag)


def problems_after_reparse(html: str) -> list[str]:
    doc = html5lib.parse(f'<!doctype html><html><body><div>{html}</div></body></html>', namespaceHTMLElements=True)
    problems = []
    for el in doc.iter():
        if not isinstance(el.tag, str):
            continue  # comment
        ns, name = split_ns(el.tag)
        if ns == SVG or name in FORBIDDEN_ELEMENTS:
            problems.append(f'element {name}')
        if name == 'iframe':
            if not (el.get('src') or '').startswith('https://www.youtube'):
                problems.append(f'iframe src {el.get("src")}')
            if el.text or len(el):
                problems.append('iframe has content')
        if name == 'input' and el.get('type') != 'checkbox':
            problems.append(f'input type {el.get("type")}')
        for attr, val in el.attrib.items():
            attr = split_ns(attr)[1].lower()
            if attr.startswith('on') or attr in ('srcdoc', 'formaction'):
                problems.append(f'attr {attr}')
            if attr in URL_ATTRS and bad_url(val):
                problems.append(f'url {attr}={val!r}')
            if attr == 'style' and re.search(r'url|expression|binding|behavior|\\|position|@import', val, re.I):
                problems.append(f'style {val!r}')
    return problems


def setup_module():
    setup_basic_test()
    setup_unit_test()
    setup_with_tools()


@td.with_wiki
def setup_with_tools():
    setup_global_objects()


@pytest.mark.parametrize('convert', [h.clean_html, lambda text: g.markdown.convert(text)], ids=['clean_html', 'markdown'])
def test_sanitized_output_is_safe_after_reparse(convert):
    failures = []
    for payload in build_corpus():
        output = str(convert(payload))
        failures += [(problem, payload, output) for problem in problems_after_reparse(output)]
    assert failures[:10] == []
