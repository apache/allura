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


from urllib.parse import urlparse

from tg import tmpl_context as c
from tg import request, url
import json
import logging

from formencode import validators as fev
import paginate

import ew as ew_core
import ew.jinja2_ew as ew
import six

from allura.lib import validators as v


log = logging.getLogger(__name__)


def onready(text):
    return ew.JSScript('$(function () {%s});' % text)


class LabelList(v.UnicodeString):

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('if_empty', [])
        super().__init__(*args, **kwargs)

    def _to_python(self, value, state):
        value = super()._to_python(value, state)
        return value.split(',')

    def _from_python(self, value, state):
        value = ','.join(value)
        value = super()._from_python(value, state)
        return value


class LabelEdit(ew.InputField):
    template = 'jinja:allura:templates/widgets/label_edit.html'
    validator = LabelList(if_empty=[])
    defaults = dict(
        ew.InputField.defaults,
        name=None,
        value=None,
        className='',
        show_label=True,
        placeholder=None)

    def from_python(self, value, state=None):
        if isinstance(value, str):
            return value
        elif value is None:
            return ''
        else:
            return ','.join(value)

    def resources(self):
        yield ew.JSLink('allura/js/jquery-ui-1.13.2.min.js', location='body_top_js')
        yield ew.JSLink('js/jquery.tagsinput.js')
        yield ew.CSSLink('css/jquery.tagsinput.css')
        yield onready('''
          $('input.label_edit').tagsInput({
              'height':'100%%',
              'width':'100%%',
              'autocomplete_url':'%(url)stags'
          });
          $('form').on('blur', '.ui-autocomplete-input', function() {
              setTimeout(function(){
                  var clicked = $(document.activeElement); // This is the element that has focus
                  if (clicked.is('#ui-active-menuitem')) {
                      return false;
                  } else {
                      var value = $('div.tagsinput div input').val();
                      var exists = $('input.label_edit').tagExist(value);
                      var default_value = $('div.tagsinput div input').attr('data-default');
                      if ((value !== default_value) && (!exists) && value !== '') {
                          $('input.label_edit').addTag(value);
                      }
                      $('input[type=submit]', this).prop('disabled', true);
                  }
                }, 1);
            });
        ''' % dict(url=c.app.url))


class ProjectUserSelect(ew.InputField):
    template = 'jinja:allura:templates/widgets/project_user_select.html'
    defaults = dict(
        ew.InputField.defaults,
        name=None,
        value=None,
        show_label=True,
        className=None)

    def __init__(self, **kw):
        super().__init__(**kw)
        if not isinstance(self.value, list):
            self.value = [self.value]

    def from_python(self, value, state=None):
        return value

    def resources(self):
        yield from super().resources()
        yield ew.JSLink('allura/js/jquery-ui-1.13.2.min.js', location='body_top_js')
        yield ew.CSSLink('css/autocomplete.css')  # customized in [6b78ed] so we can't just use jquery-ui.min.css
        yield onready('''
          $('input.project_user_select').autocomplete({
            source: function (request, response) {
              $.ajax({
                url: "%suser_search",
                dataType: "json",
                data: {
                  term: request.term
                },
                success: function (data) {
                  response(data.users);
                }
              });
            },
            minLength: 2
          });''' % c.project.url())


class ProjectUserCombo(ew.SingleSelectField):
    template = 'jinja:allura:templates/widgets/project_user_combo.html'

    # No options for widget initially.
    # It'll be populated later via ajax call.
    options = []

    def to_python(self, value, state):
        # Skipping validation, 'cause widget has no values initially.
        # All values loaded later via ajax.
        return value

    def resources(self):
        yield from super().resources()
        yield ew.JSLink('allura/js/jquery-ui-1.13.2.min.js', location='body_top_js')
        yield ew.CSSLink('css/autocomplete.css')  # customized in [6b78ed] so we can't just use jquery-ui.min.css
        yield ew.CSSLink('css/combobox.css')
        yield ew.JSLink('js/combobox.js')
        yield onready('''
          $('select.project-user-combobox').combobox({
            source_url: "%susers"
          });''' % c.project.url())


class NeighborhoodProjectSelect(ew.InputField):
    template = 'jinja:allura:templates/widgets/neighborhood_project_select.html'
    defaults = dict(
        ew.InputField.defaults,
        name=None,
        value=None,
        show_label=True,
        className=None)

    def __init__(self, url, **kw):
        super().__init__(**kw)
        if not isinstance(self.value, list):
            self.value = [self.value]
        self.url = url

    def from_python(self, value, state=None):
        return value

    def resources(self):
        yield from super().resources()
        yield ew.JSLink('allura/js/jquery-ui-1.13.2.min.js', location='body_top_js')
        yield ew.CSSLink('css/autocomplete.css')  # customized in [6b78ed] so we can't just use jquery-ui.min.css
        yield onready('''
          $('input.neighborhood-project-select').autocomplete({
            source: function (request, response) {
              $.ajax({
                url: "%s",
                dataType: "json",
                data: {
                  term: request.term
                },
                success: function (data) {
                  response(data.projects);
                }
              });
            },
            minLength: 3
          });''' % self.url)


class AttachmentList(ew_core.Widget):
    template = 'jinja:allura:templates/widgets/attachment_list.html'
    defaults = dict(
        ew_core.Widget.defaults,
        attachments=None,
        edit_mode=None)


class AttachmentAdd(ew_core.Widget):
    template = 'jinja:allura:templates/widgets/attachment_add.html'
    defaults = dict(
        ew_core.Widget.defaults,
        action=None,
        name=None)

    def resources(self):
        yield from super().resources()
        yield onready('''
            $(".attachment_form_add_button").click(function (evt) {
                $(this).hide();
                $(".attachment_form_fields", this.parentNode).show();
                evt.preventDefault();
            });
         ''')


class SubmitButton(ew.SubmitButton):
    attrs = {'class': 'ui-state-default ui-button ui-button-text'}


class Radio(ew.InputField):
    template = ew_core.render.Snippet('''<input {% if value %} checked{% endif %} {{widget.j2_attrs({
        'id':id,
        'type':field_type,
        'name':rendered_name,
        'class':css_class,
        'readonly':readonly,
        'value':value},
        attrs)}}>''', 'jinja2')
    defaults = dict(
        ew.InputField.defaults,
        field_type='radio')


class AutoResizeTextarea(ew.TextArea):
    defaults = dict(
        ew.TextArea.defaults,
        name=None,
        value=None,
        css_class='auto_resize')

    def resources(self):
        yield ew.JSLink('js/jquery.autosize-min.js')
        yield onready('''
            $('textarea.auto_resize').focus(function(){$(this).autosize();});
        ''')


class MarkdownEdit(ew.TextArea):
    template = 'jinja:allura:templates/widgets/markdown_edit.html'
    validator = v.UnicodeString()
    defaults = dict(
        ew.TextArea.defaults,
        name=None,
        value=None,
        show_label=True)

    def from_python(self, value, state=None):
        return value

    def resources(self):
        yield from super().resources()
        yield ew.JSLink('js/jquery.lightbox_me.js')
        yield ew.CSSLink('css/easymde.min.css', compress=False)
        yield ew.CSSLink('css/markitup_sf.css')
        yield ew.CSSLink('css/show-hint.css')
        yield ew.JSLink('js/easymde.min.js')
        yield ew.JSLink('js/sf_markitup.js')
        yield ew.JSLink('js/show-hint.js')
        yield ew.JSLink('js/usermentions-helper.js')
        yield onready('getProjectUsers(\'%s/users\')' % c.project.url())


class PageList(ew_core.Widget):
    template = 'jinja:allura:templates/widgets/page_list.html'
    defaults = dict(
        ew_core.Widget.defaults,
        name=None,
        limit=None,
        count=0,
        page=0,
        show_label=True,
        show_if_single_page=False,
        force_next=False)

    def paginator(self, count, page, limit, zero_based_pages=True):
        page_offset = 1 if zero_based_pages else 0
        limit = 10 if limit is None else limit

        def page_url(page):
            params = request.GET.copy()
            params['page'] = page - page_offset
            if params['page'] == 0:
                del params['page']
            # REQUEST_URI keeps double-slashes, but not available in all environments (like tests)
            curr_path = urlparse(request.environ.get('REQUEST_URI')).path or request.path
            return url(curr_path, params)
        return paginate.Page(list(range(count)), page + page_offset, int(limit),
                             url_maker=page_url,
                             )

    def prepare_context(self, context):
        context = super().prepare_context(context)
        count = context['count']
        page = context['page']
        limit = context['limit']
        context['paginator'] = self.paginator(count, page, limit)
        if context['force_next']:
            context['paginator'].next_page = context['paginator'].page + 1
        return context

    def resources(self):
        yield ew.CSSLink('css/page_list.css')

    @property
    def url_params(self, **kw):
        url_params = dict()
        for k, val in request.params.items():
            if k not in ['limit', 'count', 'page']:
                url_params[k] = val
        return url_params


class PageSize(ew_core.Widget):
    template = 'jinja:allura:templates/widgets/page_size.html'
    defaults = dict(
        ew_core.Widget.defaults,
        limit=None,
        name=None,
        count=0,
        show_label=False)

    @property
    def url_params(self, **kw):
        url_params = dict()
        for k, val in request.params.items():
            if k not in ['limit', 'count', 'page']:
                url_params[k] = val
        return url_params

    def resources(self):
        yield onready('''
            $('select.results_per_page').change(function () {
                this.form.submit();});''')


class JQueryMixin:
    js_widget_name = None
    js_plugin_file = None
    js_params = [
        'container_cls'
    ]
    defaults = dict(
        container_cls='container')

    def resources(self):
        yield from super().resources()
        if self.js_plugin_file is not None:
            yield self.js_plugin_file
        opts = {
            k: getattr(self, k)
            for k in self.js_params}
        yield onready('''
$(document).on('clone', function () {
    $('.%s').%s(%s); });
$(document).trigger('clone');
            ''' % (self.container_cls, self.js_widget_name, json.dumps(opts)))


class SortableRepeatedMixin(JQueryMixin):
    js_widget_name = 'SortableRepeatedField'
    js_plugin_file = ew.JSLink('js/sortable_repeated_field.js')
    js_params = JQueryMixin.js_params + [
        'field_cls',
        'flist_cls',
        'stub_cls',
        'msg_cls',
        'append_to',
        'extra_field_on_focus_name',
    ]
    defaults = dict(
        container_cls='sortable-repeated-field',
        field_cls='sortable-field',
        flist_cls='sortable-field-list',
        stub_cls='sortable-field-stub',
        msg_cls='sortable-field-message',
        append_to='top',
        empty_msg='No fields have been defined',
        nonempty_msg='Drag and drop the fields to reorder',
        show_msg=True,
        show_button=True,
        extra_field_on_focus_name=None,
        repetitions=0)

    button = ew.InputField(
        css_class='add', field_type='button', value='New Field')


class SortableRepeatedField(SortableRepeatedMixin, ew.RepeatedField):
    template = 'jinja:allura:templates/widgets/sortable_repeated_field.html'
    defaults = dict(
        ew.RepeatedField.defaults,
        **SortableRepeatedMixin.defaults)


class SortableTable(SortableRepeatedMixin, ew.TableField):
    template = 'jinja:allura:templates/widgets/sortable_table.html'
    defaults = dict(
        ew.TableField.defaults,
        **SortableRepeatedMixin.defaults)


class StateField(JQueryMixin, ew.CompoundField):
    template = 'jinja:allura:templates/widgets/state_field.html'
    js_widget_name = 'StateField'
    js_plugin_file = ew.JSLink('js/state_field.js')
    js_params = JQueryMixin.js_params + [
        'selector_cls',
        'field_cls',
    ]
    defaults = dict(
        ew.CompoundField.defaults,
        js_params=js_params,
        container_cls='state-field-container',
        selector_cls='state-field-selector',
        field_cls='state-field',
        show_label=False,
        selector=None,
        states={},
    )

    @property
    def fields(self):
        return [self.selector] + list(self.states.values())


class DateField(JQueryMixin, ew.TextField):
    js_widget_name = 'datepicker'
    js_params = JQueryMixin.js_params
    container_cls = 'ui-date-field'
    defaults = dict(
        ew.TextField.defaults,
        container_cls='ui-date-field',
        css_class='ui-date-field')

    def resources(self):
        yield from super().resources()
        yield ew.JSLink('allura/js/jquery-ui-1.13.2.min.js', location='body_top_js')
        yield ew.CSSLink('allura/css/smoothness/jquery-ui-1.13.2.min.css', compress=False)  # compress will also serve from a different location, breaking image refs


class FieldCluster(ew.CompoundField):
    template = 'jinja:allura:templates/widgets/field_cluster.html'


class AdminField(ew.InputField):

    '''Field with the correct layout/etc for an admin page'''
    template = 'jinja:allura:templates/widgets/admin_field.html'
    defaults = dict(
        ew.InputField.defaults,
        field=None,
        css_class=None,
        errors=None)

    def __init__(self, **kw):
        super().__init__(**kw)
        for p in self.field.get_params():
            setattr(self, p, getattr(self.field, p))

    def resources(self):
        yield from self.field.resources()


class Lightbox(ew_core.Widget):
    template = 'jinja:allura:templates/widgets/lightbox.html'
    defaults = dict(
        name=None,
        trigger=None,
        options='',
        content='',
        content_template=None)

    def resources(self):
        yield ew.JSLink('js/jquery.lightbox_me.js')
        yield onready('''
            var $lightbox = $('#lightbox_%s');
            $('body').on('click', '%s', function(e) {
                e.preventDefault();
                $lightbox.lightbox_me(%s);
            });
            $lightbox.on('click', '.close', function(e) {
                e.preventDefault();
                $lightbox.trigger('close');
            });
        ''' % (self.name, self.trigger, self.options))


class DisplayOnlyField(ew.HiddenField):

    '''
    Render a field as plain text, optionally with a hidden field to preserve the value.
    '''
    template = ew.Snippet('''{{ (text or value or attrs.value)|e }}
        {%- if with_hidden_input is none and name or with_hidden_input -%}
        <input {{
            widget.j2_attrs({
                'type':'hidden',
                'name':name,
                'value':value,
                'class':css_class}, attrs)
        }}>
        {%- endif %}''', 'jinja2')
    defaults = dict(
        ew.HiddenField.defaults,
        text=None,
        value=None,
        with_hidden_input=None)
