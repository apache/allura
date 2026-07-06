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
Proof of concept: sanitize with turbohtml.clean's Policy-based sanitizer instead of
our hand-rolled tree walk in ForgeHTMLSanitizer.

turbohtml.clean has a non-overridable safety baseline that never allows <iframe>,
and no way to conditionally allow an element based on its attributes (we allow
iframes only from youtube embed URLs, and <input> only for checkboxes).  To work
around that, valid iframes/checkbox-inputs are stashed and replaced with placeholder
elements before sanitizing, then restored afterwards.  Placeholders carry a per-call
random nonce so user content can't forge one.

The library then handles: element/attribute whitelisting, escaping disallowed tags,
URL scheme checks (including obfuscated javascript: forms), CSS scrubbing of style
attributes, and comment removal.  We keep: the conditional iframe/checkbox rules
(the placeholder dance), class/id/data-URI filtering (Policy.attribute_filter), and
the misleading-link suffixes (a post-pass that also restores the placeholders).
"""

import logging
import secrets

from turbohtml import parse_fragment, Element, Text
from turbohtml.clean import Policy, Sanitizer, DEFAULT_CSS_PROPERTIES

from allura.lib.utils import ForgeHTMLSanitizer

log = logging.getLogger(__name__)


class PlaceholderForgeHTMLSanitizer(ForgeHTMLSanitizer):

    PLACEHOLDER_ATTR = 'data-allura-placeholder'

    def __init__(self):
        super().__init__()
        self._policy = Policy(
            # iframe & input are excluded: invalid ones get escaped by the library,
            # valid ones bypass it entirely via the placeholder stash
            tags=frozenset(self.allowed_elements - {'iframe', 'input'}),
            attributes={'*': frozenset(self.allowed_attributes | {self.PLACEHOLDER_ATTR})},
            url_schemes=frozenset(self.allowed_url_schemes),
            attribute_filter=self._attribute_filter,
            # DEFAULT_CSS_PROPERTIES is html5lib's whitelist; add the shorthands our
            # sanitize_css() allowed (the library scrubs url()/expression() in values)
            css_properties=frozenset(DEFAULT_CSS_PROPERTIES | {'background', 'border', 'margin', 'padding'}),
        )

    def sanitize(self, html: str) -> str:
        root = parse_fragment(html)
        nonce = secrets.token_hex(8)
        stash = self._stash_conditional_elements(root, nonce)
        cleaned = Sanitizer(self._policy).sanitize(root.inner_html)
        return self._restore_and_finish(cleaned, nonce, stash)

    def _stash_conditional_elements(self, root, nonce: str) -> list[Element]:
        """
        Detach valid iframes/checkbox-inputs, leaving nonce-marked placeholders.
        Invalid ones are left in place for the library to escape.
        """
        stash = []
        for el in list(root.find_all(['iframe', 'input'])):
            if el.tag == 'iframe':
                ok = (el.attrs.get('src') or '').startswith(self.valid_iframe_srcs)
            else:
                ok = el.attrs.get('type') == 'checkbox'
            if ok:
                # stashed elements bypass the library, so whitelist their attributes ourselves
                self._sanitize_attrs(el)
                if el.tag == 'iframe':
                    el.clear()  # iframe contents are fallback-only, and would serialize unescaped
                placeholder = Element('span', {self.PLACEHOLDER_ATTR: f'{nonce}-{len(stash)}'})
                el.replace_with(placeholder)
                stash.append(el)
        return stash

    def _attribute_filter(self, tag: str, attr: str, value: str) -> str | None:
        # scheme filtering is handled by Policy.url_schemes; this adds our extra rules
        if attr in self._url_attributes and not self._url_allowed(value):
            return None  # e.g. a data: URI that isn't one of the allowed image types
        if attr == 'class':
            classes = value.split()
            cleaned_classes = [c for c in classes
                               if c in self.valid_class_values or c.startswith(self.valid_partial_class_prefixes)]
            if cleaned_classes != classes:
                log.info(f'Removed invalid classes: {classes} => {cleaned_classes}')
            return ' '.join(cleaned_classes)
        if attr == 'id':
            if not any(value.startswith(prefix) for prefix in self.valid_id_prefixes):
                return 'user-content-' + value
        return value

    def _restore_and_finish(self, cleaned: str, nonce: str, stash: list[Element]) -> str:
        root = parse_fragment(cleaned)
        used = set()
        for placeholder in list(root.find_all('span')):
            marker = placeholder.attrs.get(self.PLACEHOLDER_ATTR)
            if marker is None:
                continue
            marker_nonce, _, index_str = marker.rpartition('-')
            index = int(index_str) if index_str.isdigit() else -1
            if marker_nonce == nonce and 0 <= index < len(stash) and index not in used:
                used.add(index)
                placeholder.replace_with(stash[index])
            else:
                # forged placeholder from user content: keep it as a plain span
                del placeholder.attrs[self.PLACEHOLDER_ATTR]

        for link in root.find_all('a'):
            suffix = self._link_suffix(link)
            if suffix:
                link.insert_after(Text(suffix))

        return root.inner_html
