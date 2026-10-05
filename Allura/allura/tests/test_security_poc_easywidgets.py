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

"""Regression tests for EasyWidgets security fixes.

Each test is a proof-of-concept asserting the *secure* outcome: it fails on EasyWidgets 0.4.3 and
passes once the issue is fixed.  Only the tracker select-option XSS is exploitable through a form
in stock Allura; the unbounded _slim cache is an unauthenticated DoS.  The rest are library
primitives or hardening, as each class docstring says.  TestKnownOpen is xfail; an XPASS means
someone fixed it.

Unit-level: no MongoDB, Solr or WSGI app needed::

    cd Allura && pytest allura/tests/test_security_poc_easywidgets.py
"""

import html
import os
import re

import ew
import ew.jinja2_ew as jew
import pytest
from bs4 import BeautifulSoup
from ew import widget_context
from ew.core import WidgetContext
from ew.render import TemplateEngine
from ew.resource import ResourceManager
from ew.utils import Bunch, push_context
from paste.registry import Registry

from allura.lib import helpers as h
from allura.lib.widgets.forms import _HTMLExplanation

try:
    from forgetracker.widgets.ticket_form import MilestoneField, TicketCustomField
except ImportError:  # ForgeTracker not installed alongside Allura
    MilestoneField = TicketCustomField = None

needs_forgetracker = pytest.mark.skipif(TicketCustomField is None, reason='ForgeTracker not installed')

# Typed into a select field's "Options" box; shlex unescapes \" so a bare " survives
SELECT_OPTIONS_EXPLOIT = r'"x\" onmouseover=alert(document.domain) autofocus onfocus=alert(1) y"'

# Breaks out of value="..." if unescaped
ATTR_BREAKOUT = 'x" onmouseover=alert(document.domain) autofocus onfocus=alert(1) y'

# Breaks out of element text if unescaped
TEXT_BREAKOUT = '<img src=x onerror=alert(document.domain)>'


@pytest.fixture(autouse=True)
def ew_widget_context():
    """Per-request widget context and clean ResourceManager, as WidgetMiddleware sets up; restored after."""
    saved_engines = TemplateEngine._engines
    saved_paths = ResourceManager.paths
    saved_cache = ResourceManager.resource_cache
    TemplateEngine.initialize({})
    ResourceManager.paths = []
    ResourceManager.resource_cache = {}
    registry = Registry()
    registry.prepare()
    manager = ResourceManager()
    registry.register(widget_context, WidgetContext(scheme='http', resource_manager=manager))
    yield manager
    registry.cleanup()
    TemplateEngine._engines = saved_engines
    ResourceManager.paths = saved_paths
    ResourceManager.resource_cache = saved_cache


def soup(markup):
    return BeautifulSoup(markup, 'html.parser')


def event_handler_attrs(markup):
    """Every on*= attribute the browser would parse out of the markup."""
    found = set()
    for tag in soup(markup).find_all():
        found.update(name for name in tag.attrs if name.startswith('on'))
    return found


class TestTemplateTextEvaluatedAsPython:
    """CoreEngine resolved ${...} with a bare eval(), so any text rendered through
    the default core-ew engine (Snippet(text), Widget.expand()) ran as code.

    Reachability: latent.  Nothing in this tree feeds attacker-controlled text to core-ew.
    """

    def test_snippet_does_not_import_modules(self):
        rendered = ew.Snippet('${__import__("os")}')({})
        assert 'module' not in rendered
        assert 'posix' not in rendered

    def test_snippet_does_not_execute_calls(self, tmp_path):
        canary = tmp_path / 'ew1_snippet.txt'
        payload = f'${{__import__("os").popen("touch {canary}").read()}}'
        ew.Snippet(payload)({})
        assert not canary.exists()

    def test_html_field_does_not_execute_calls(self, tmp_path):
        """HTMLField runs its text through expand(), so the eval() primitive is reachable from a widget."""
        canary = tmp_path / 'ew1_htmlfield.txt'
        payload = f'${{__import__("os").popen("touch {canary}").read()}}'
        jew.HTMLField(text=payload).display()
        assert not canary.exists()

    def test_html_escape_is_not_a_defense(self, tmp_path):
        """A payload built from bytes([...]).decode() has nothing for html.escape() to change."""
        canary = tmp_path / 'ew1_escaped.txt'
        cmd = f'touch {canary}'
        payload = '${{__import__(bytes({os_!r}).decode()).popen(bytes({cmd_!r}).decode()).read()}}'.format(
            os_=list(b'os'), cmd_=list(cmd.encode()))
        escaped = html.escape(payload)
        assert escaped == payload
        jew.HTMLField(text=escaped).display()
        assert not canary.exists()

    def test_dunder_attribute_access_is_rejected(self):
        rendered = ew.Snippet('${obj.__class__}')(dict(obj=object()))
        assert 'type' not in rendered
        assert 'object' not in rendered

    @pytest.mark.parametrize(('template', 'context', 'expected'), [
        ('${value+4}', dict(value=1), '${value+4}'),
        ('${name}', dict(name='bob'), 'bob'),
        ("${obj['k']}", dict(obj={'k': 'v'}), "${obj['k']}"),
        ('${a.b}', dict(a=Bunch(b='nested')), '${a.b}'),
        ('${x if y else z}', dict(x='yes', y=True, z='no'), '${x if y else z}'),
    ])
    def test_template_expression_syntax_not_supported(self, template, context, expected):
        assert ew.Snippet(template)(context) == expected


class TestAutoescapeOff:
    """The widget jinja2 environment had autoescape off and the bundled templates
    interpolated values with no |e.  Widget output is Markup, so Allura's own environment passes it
    through.

    Reachability: mixed.  Select-option values are live (see the tracker tests).  Other sinks only get
    developer-controlled text from Allura today (hardening), but tools outside this repo can reach them.
    """

    def test_jinja2_engine_autoescapes_by_default(self):
        assert TemplateEngine.get_engine('jinja2')._environ.autoescape is True

    def test_autoescape_is_still_configurable(self):
        TemplateEngine.initialize({'jinja2.autoescape': False})
        assert TemplateEngine.get_engine('jinja2')._environ.autoescape is False

    def test_allura_middleware_sets_autoescape_for_the_widget_env(self):
        """Allura must set autoescape for the widget env too, so an older EasyWidgets can't render unescaped."""
        middleware_py = os.path.join(os.path.dirname(h.__file__), '..', 'config', 'middleware.py')
        with open(middleware_py, encoding='utf-8') as fp:
            source = fp.read()
        assert re.search(r"""['"]jinja2\.autoescape['"]\s*:""", source)

    def test_select_field_option_value(self):
        """select_field.html: value="{{o.html_value}}" """
        field = jew.SingleSelectField(
            name='x', options=[jew.Option(label='a', py_value='a', html_value=ATTR_BREAKOUT)])
        rendered = field.display()
        assert event_handler_attrs(rendered) == set()

    def test_checkbox_set_option_value_and_labels(self):
        """checkbox_set.html: {{label}}, {{o.label}}, value="{{o.html_value}}" """
        field = jew.CheckboxSet(
            name='cs', label=TEXT_BREAKOUT,
            options=[jew.Option(label=TEXT_BREAKOUT, py_value='v', html_value=ATTR_BREAKOUT)])
        rendered = field.display()
        assert event_handler_attrs(rendered) == set()
        assert soup(rendered).find('img') is None

    def test_checkbox_label(self):
        """checkbox.html: {{label}} """
        rendered = jew.Checkbox(name='cb', label=TEXT_BREAKOUT).display()
        assert soup(rendered).find('img') is None

    def test_ew_lib_field_label(self):
        """_ew_lib.html subfields(): <label ...>{{field.label}}</label> """
        form = jew.SimpleForm(fields=[jew.TextField(name='f', label=TEXT_BREAKOUT)])
        rendered = form.display()
        assert soup(rendered).find('img') is None

    def test_ew_lib_field_errors(self):
        """_ew_lib.html subfields(): <span ...>{{ctx.errors}}</span> """
        form = jew.SimpleForm(fields=[jew.TextField(name='f', label='ok')])
        rendered = form.display(errors={'f': TEXT_BREAKOUT})
        assert soup(rendered).find('img') is None

    def test_ew_lib_table_column_label(self):
        """_ew_lib.html table(): <th>{{col.label}}</th> """
        field = jew.TableField(name='t', fields=[jew.TextField(name='f', label=TEXT_BREAKOUT)], repetitions=1)
        rendered = field.display()
        assert soup(rendered).find('img') is None

    def test_row_field_errors(self):
        """row_field.html: <span ...>{{ctx.errors}}</span> """
        field = jew.RowField(name='r', fields=[jew.TextField(name='f')])
        rendered = field.display(errors={'f': TEXT_BREAKOUT})
        assert soup(rendered).find('img') is None

    def test_repeated_field_errors(self):
        """repeated_field.html: <span ...>{{ctx.errors}} """
        field = jew.RepeatedField(name='rep', field=jew.TextField(name='f'), repetitions=1)
        rendered = field.display(errors={0: TEXT_BREAKOUT})
        assert soup(rendered).find('img') is None

    def test_js_link_href(self, ew_widget_context):
        """JSLink's snippet: src="{{widget.href}}" """
        link = jew.JSLink('x.js" onload=alert(document.domain) a="')
        link.manager = ew_widget_context
        assert event_handler_attrs(link.display()) == set()

    def test_css_link_href(self, ew_widget_context):
        """CSSLink's snippet: href="{{widget.href}}" """
        link = jew.CSSLink('x.css" onload=alert(document.domain) a="')
        link.manager = ew_widget_context
        assert event_handler_attrs(link.display()) == set()

    def test_google_analytics_account_cannot_break_out_of_the_script(self, ew_widget_context):
        """google_analytics.html: inside a <script>, so the account must be a JS literal (|tojson)."""
        ga = jew.GoogleAnalytics("UA-1'); alert(document.domain); ('")
        ga.manager = ew_widget_context
        assert "'); alert(document.domain); ('" not in ga.display()

    def test_script_and_style_bodies_are_still_emitted_as_markup(self, ew_widget_context):
        """JSScript/CSSScript bodies are markup by definition and must stay unescaped."""
        script = jew.JSScript('if (a && b) { c(); }')
        script.manager = ew_widget_context
        assert 'a && b' in script.display()
        style = jew.CSSScript('a > b { color: red }')
        style.manager = ew_widget_context
        assert 'a > b' in style.display()

    def test_html_explanation_still_renders_its_markup(self):
        """forms.py:46 relied on autoescape being off, so it needs an explicit |safe."""
        rendered = _HTMLExplanation(text='<b>explanation</b>').display()
        assert '<b>explanation</b>' in rendered


class TestTrackerSelectOptionsStoredXss:
    """split_select_field_options() stripped double quotes only when shlex failed; on
    success shlex unescapes \" and the quote reached select_field.html's unescaped value="...".

    Reachability: live, the only finding here that is.  An admin types the payload into Admin ->
    Custom Fields -> Options and it runs for every user who opens the ticket form.  Milestone names
    reach the same sink.
    """

    def test_split_select_field_options_strips_quotes_on_the_shlex_success_path(self):
        options = h.split_select_field_options(SELECT_OPTIONS_EXPLOIT)
        assert not any('"' in opt for opt in options)

    def test_split_select_field_options_strips_quotes_on_the_shlex_failure_path(self):
        options = h.split_select_field_options('a "b')
        assert not any('"' in opt for opt in options)

    @pytest.mark.parametrize(('raw', 'expected'), [
        ('"one two" three', ['one two', 'three']),
        ('*default other', ['*default', 'other']),
        ('a b c', ['a', 'b', 'c']),
    ])
    def test_split_select_field_options_normal_usage(self, raw, expected):
        assert h.split_select_field_options(raw) == expected

    @needs_forgetracker
    def test_ticket_select_custom_field_renders_no_attribute_breakout(self):
        field = Bunch(name='_test', label='Test', type='select', options=SELECT_OPTIONS_EXPLOIT)
        rendered = TicketCustomField.SELECTOR['select'](field).display()
        assert event_handler_attrs(rendered) == set()

    @needs_forgetracker
    def test_milestone_field_renders_no_attribute_breakout(self):
        """MilestoneField's own unescaped value= sink, fed by milestone names."""
        option = jew.Option(label='v1', py_value='v1', html_value=ATTR_BREAKOUT, complete=False)
        rendered = MilestoneField(label='M', name='m', options=[option]).display()
        assert event_handler_attrs(rendered) == set()


class TestPathContainment:
    """get_filename() accepted any path that merely startswith() the registered
    directory, so a sibling like static-private/ was reachable.

    Reachability: not exploitable in stock Allura; customised deployments or third-party themes can.
    """

    @pytest.fixture
    def tree(self, tmp_path):
        public = tmp_path / 'static'
        public.mkdir()
        (public / 'app.js').write_text('ok')
        private = tmp_path / 'static-private'
        private.mkdir()
        (private / 'secret.key').write_text('SECRET')
        backup = tmp_path / 'static.bak'
        backup.mkdir()
        (backup / 'id_rsa').write_text('PRIVATE KEY')
        ResourceManager.register_directory('static', str(public))
        return tmp_path

    @pytest.mark.parametrize('res_path', [
        'static/../../etc/passwd',
        'static/../static-private/secret.key',
        'static/../static.bak/id_rsa',
    ])
    def test_paths_outside_the_registered_directory_are_refused(self, tree, res_path):
        assert ResourceManager().get_filename(res_path) is None

    def test_registered_directory_is_still_served(self, tree):
        assert ResourceManager().get_filename('static/app.js') == str(tree / 'static' / 'app.js')


class TestUnboundedResourceCache:
    """ResourceManager.resource_cache is shared, keyed on the raw href, and has no
    bound or eviction.  WidgetMiddleware serves /_ew_resources/ with no session required.

    Reachability: live and unauthenticated, but a memory-exhaustion DoS, not an injection.
    """

    FILES_PER_REQUEST = 100
    BIG_FILE_BYTES = 64 * 1024
    DEFAULT_CACHE_BUDGET = 64 * 1024 * 1024

    @pytest.fixture
    def static_dir(self, tmp_path):
        public = tmp_path / 'static'
        public.mkdir()
        (public / 'f0.js').write_text('x' * 1024)
        for i in range(self.FILES_PER_REQUEST):
            (public / f'big{i}.js').write_text('x' * self.BIG_FILE_BYTES)
        ResourceManager.register_directory('static', str(public))
        return public

    def test_one_slim_request_cannot_concatenate_files_without_bound(self, static_dir):
        """One small request naming the same file repeatedly (~125x amplification).  With
        max_slim_hrefs the response stops growing at the cap."""
        big = ResourceManager(use_cache=True).serve_slim('js', ';'.join(['static/f0.js'] * 1000))
        huge = ResourceManager(use_cache=True).serve_slim('js', ';'.join(['static/f0.js'] * 10000))
        assert len(huge) == len(big)

    def test_cache_does_not_grow_with_every_distinct_request(self, static_dir):
        """Serve more unique content than the budget; a bounded cache must retain less than it served.
        Each request rotates the file list, so every href is a distinct key."""
        budget = getattr(ResourceManager, 'max_cache_bytes', self.DEFAULT_CACHE_BUDGET)
        per_request = min(self.FILES_PER_REQUEST,
                          getattr(ResourceManager, 'max_slim_hrefs', self.FILES_PER_REQUEST))
        names = [f'static/big{i}.js' for i in range(per_request)]
        requests = int(budget * 1.5 / (per_request * self.BIG_FILE_BYTES)) + 1
        assert requests <= per_request
        served = 0
        for i in range(requests):
            href = ';'.join(names[i:] + names[:i])
            served += len(ResourceManager(use_cache=True).serve_slim('js', href))
        cached = sum(len(v) for v in ResourceManager.resource_cache.values())
        assert served > budget
        assert cached < served


class TestLatentRceViaHtmlField:
    """forms.py:606 builds ew.HTMLField(text=html.escape(cat.shortname)).  Not
    exploitable, but not because of html.escape() (see the eval() tests); h.slugify() in
    TroveCategoryController._create strips $ { } ( ) before storage.  Both halves are asserted.

    Only the inner sink is exercised; the whole form needs a full app context.

    Reachability: latent.  _create is the only writer of shortname and always slugifies.
    """

    def test_the_html_field_sink_does_not_execute_the_shortname(self, tmp_path):
        canary = tmp_path / 'a2.txt'
        cmd = f'touch {canary}'
        shortname = '${{__import__(bytes({os_!r}).decode()).popen(bytes({cmd_!r}).decode()).read()}}'.format(
            os_=list(b'os'), cmd_=list(cmd.encode()))
        jew.HTMLField(text=html.escape(shortname), attrs={'disabled': True, 'value': shortname}).display()
        assert not canary.exists()

    def test_slugify_strips_expression_syntax(self):
        """The accidental defense; pinned so a slug-rule refactor is visible."""
        slug, _ = h.slugify("${__import__('os').popen('id')}")
        for ch in '${}()\'':
            assert ch not in slug


class TestPushContextNotExceptionSafe:
    """push_context() had no try/finally, so a render error left widget_context pointing
    at the wrong widget while the error page rendered.

    Reachability: not attacker-triggered; a robustness fix.
    """

    def test_attributes_are_restored_when_the_body_raises(self):
        class Target:
            existing = 'original'

        obj = Target()
        with pytest.raises(RuntimeError), push_context(obj, existing='temporary', added='new'):
            raise RuntimeError('render failed')
        assert obj.existing == 'original'
        assert not hasattr(obj, 'added')

    def test_widget_context_is_restored_when_a_widget_raises(self):
        class Exploding(ew.Widget):
            def template(self, context):
                raise RuntimeError('render failed')

        before = widget_context.widget
        with pytest.raises(RuntimeError):
            Exploding().display()
        assert widget_context.widget is before


class TestInternalErrorTextRendered:
    """'[Exception in <expr>: <message>]' was rendered into the response.

    Reachability: information disclosure to anyone who can make a template expression fail.
    """

    def test_exception_detail_is_not_rendered_into_the_page(self):
        class Boom:
            def __getattr__(self, name):
                raise RuntimeError('SECRET_INTERNAL_DETAIL')

        rendered = ew.Snippet('${obj.attr}')(dict(obj=Boom()))
        assert 'SECRET_INTERNAL_DETAIL' not in rendered


class TestKnownOpen:
    """Issues deliberately left open; xfail, so XPASS means one got fixed."""

    @pytest.mark.xfail(reason='per-render state on shared Option instances is a design change')
    def test_option_selection_does_not_persist_across_renders(self):
        """SelectField writes selected/html_value onto Option instances that are usually shared, so
        selection state can bleed between concurrent requests."""
        option = jew.Option(label='a', py_value='a', html_value='a')
        field = jew.SingleSelectField(name='x', options=[option])
        field.display(value='a')
        field.display(value=None)
        assert option.selected is False

    @pytest.mark.xfail(reason="LinkField javascript: guard would break legitimate javascript:void(0)")
    def test_link_field_rejects_javascript_scheme(self):
        rendered = jew.LinkField().display(value='javascript:alert(document.domain)')
        assert 'javascript:' not in rendered

    @pytest.mark.xfail(reason='_attr() validates values but not attribute names; every attrs dict in Allura '
                              'is developer-controlled today')
    def test_attr_names_cannot_inject_an_attribute(self):
        rendered = jew.InputField(name='x', attrs={'y onmouseover=alert(document.domain)': 'z'}).display()
        assert event_handler_attrs(rendered) == set()
