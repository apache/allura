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

"""End-to-end test for stored XSS via select custom-field options.

A tracker admin POSTs the payload to the custom-fields admin endpoint and a different user's ticket
form renders it.  Library-level cases are unit-tested in
``Allura/allura/tests/test_security_poc_easywidgets.py``.

Assertions are structural: the page may still contain the payload text inside an attribute value,
but must not contain an ``on*`` attribute the browser would parse out.

Needs a full Allura runtime (MongoDB, Solr)::

    cd ForgeTracker && pytest forgetracker/tests/functional/test_security_a1_select_options_xss.py
"""

from formencode.variabledecode import variable_encode

from forgetracker import model as tm
from forgetracker.tests.functional.test_root import TrackerTestController

# Typed into a select field's "Options" box; shlex unescapes \" so a bare " reaches value="..."
OPTIONS_PAYLOAD = r'"x\" onmouseover=alert(document.domain) autofocus onfocus=alert(1) y"'

# Same breakout, closing the element instead of the attribute
ELEMENT_PAYLOAD = r'"x\"><script>alert(document.domain)</script>"'

# Milestone names only get .replace("/", "-"), so a quote reaches the same sink
MILESTONE_PAYLOAD = r'1.0" onmouseover=alert(document.domain) x'

FIELD_NAME = '_testselect'
MILESTONE_FIELD_NAME = '_releases'


def event_handler_attrs(tag):
    """Every on*= attribute a browser would parse out of this subtree."""
    found = set()
    for el in [tag, *tag.find_all()]:
        found.update(name for name in el.attrs if name.startswith('on'))
    return found


class TestSelectOptionsStoredXss(TrackerTestController):

    def _post_select_field(self, options):
        params = dict(
            custom_fields=[
                dict(name=FIELD_NAME, label='Test', type='select', options=options),
            ],
            open_status_names='aa bb',
            closed_status_names='cc',
        )
        self.app.post('/admin/bugs/set_custom_fields', params=variable_encode(params))

    def _post_milestone_field(self, milestone_name):
        params = dict(
            custom_fields=[
                dict(label='releases', show_in_search='on', type='milestone',
                     milestones=[dict(name=milestone_name)]),
            ],
            open_status_names='aa bb',
            closed_status_names='cc',
        )
        self.app.post('/admin/bugs/set_custom_fields', params=variable_encode(params))

    def _select_for(self, resp, field_name):
        """The custom field's <select>, matched by name suffix (rendered names carry a form prefix)."""
        selects = [s for s in resp.html.find_all('select')
                   if (s.get('name') or '').endswith(field_name)]
        assert len(selects) == 1
        return selects[0]

    def _stored_options(self, field_name):
        for globals_ in tm.Globals.query.find().all():
            for custom_field in globals_.custom_fields or []:
                if custom_field['name'] == field_name:
                    return custom_field['options']
        raise AssertionError(f'no stored custom field named {field_name}')

    def test_option_value_cannot_break_out_of_the_value_attribute(self):
        """Pre-fix, the option rendered onmouseover/autofocus/onfocus attributes."""
        self._post_select_field(OPTIONS_PAYLOAD)
        select = self._select_for(self.app.get('/bugs/new/'), FIELD_NAME)
        assert event_handler_attrs(select) == set()
        assert 'autofocus' not in select.find('option').attrs

    def test_payload_reaches_every_user_who_opens_the_form(self):
        """The admin stores it; any logged-in user (*authenticated can 'create') renders it."""
        self._post_select_field(OPTIONS_PAYLOAD)
        victim = self.app.get('/bugs/new/', extra_environ=dict(username='test-user'))
        select = self._select_for(victim, FIELD_NAME)
        assert event_handler_attrs(select) == set()

    def test_payload_is_stored_verbatim_so_the_defence_must_be_at_render_time(self):
        """Input isn't sanitised, so the fix is at render time and covers already-stored payloads."""
        self._post_select_field(OPTIONS_PAYLOAD)
        assert self._stored_options(FIELD_NAME) == OPTIONS_PAYLOAD
        assert '"' in self._stored_options(FIELD_NAME)
        select = self._select_for(self.app.get('/bugs/new/'), FIELD_NAME)
        assert event_handler_attrs(select) == set()

    def test_option_value_cannot_close_the_element_and_add_markup(self):
        """The payload must not add elements inside the select."""
        self._post_select_field(ELEMENT_PAYLOAD)
        select = self._select_for(self.app.get('/bugs/new/'), FIELD_NAME)
        assert select.find('script') is None
        assert select.find_all('option')

    def test_field_label_is_not_a_second_hole(self):
        """The label is escaped by ticket_custom_fields.html; moving it into the widget would reopen this."""
        params = dict(
            custom_fields=[
                dict(name=FIELD_NAME, label=r'<img src=x onerror=alert(document.domain)>',
                     type='select', options='one two'),
            ],
            open_status_names='aa bb',
            closed_status_names='cc',
        )
        self.app.post('/admin/bugs/set_custom_fields', params=variable_encode(params))
        resp = self.app.get('/bugs/new/')
        label = resp.html.find('label', attrs={'for': lambda v: bool(v) and v.endswith(FIELD_NAME)})
        assert label is not None
        assert label.find('img') is None

    def test_milestone_name_cannot_break_out_of_the_value_attribute(self):
        """MilestoneField has its own value= sink.  Names are escaped, not stripped, to round-trip."""
        self._post_milestone_field(MILESTONE_PAYLOAD)
        select = self._select_for(self.app.get('/bugs/new/'), MILESTONE_FIELD_NAME)
        assert event_handler_attrs(select) == set()
        assert '"' in select.find('option')['value']
