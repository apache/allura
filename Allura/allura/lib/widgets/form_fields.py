from pylons import c
from tg import request, url
import json
import logging

from formencode import validators as fev
from webhelpers import paginate

import ew as ew_core
import ew.jinja2_ew as ew

log = logging.getLogger(__name__)

def onready(text):
    return ew.JSScript('$(function () {%s});' % text);

class LabelList(fev.UnicodeString):

    def _to_python(self, value, state):
        value = super(LabelList, self)._to_python(value, state)
        return value.split(',')

    def _from_python(self, value, state):
        value = ','.join(value)
        value = super(LabelList, self)._from_python(value, state)
        return value

class LabelEdit(ew.InputField):
    template='jinja:allura:templates/widgets/label_edit.html'
    validator = LabelList()
    defaults=dict(
        ew.InputField.defaults,
        name=None,
        value=None,
        className='',
        show_label=True,
        placeholder=None)

    def from_python(self, value, state=None):
        if isinstance(value, basestring):
            return value
        else:
            return ','.join(value)

    def resources(self):
        yield ew.JSLink('js/jquery.tag.editor.js')
        yield ew.CSSLink('css/tagEditor.css')
        yield onready('''
          $('input.label_edit').tagEditor({
            confirmRemoval: false,
            completeOnSeparator: true,
            completeOnBlur: true
          });
        ''')

class ProjectUserSelect(ew.InputField):
    template='jinja:allura:templates/widgets/project_user_select.html'
    defaults=dict(
        ew.InputField.defaults,
        name=None,
        value=None,
        show_label=True,
        className=None)

    def __init__(self, **kw):
        super(ProjectUserSelect, self).__init__(**kw)
        if not isinstance(self.value, list):
            self.value=[self.value]

    def from_python(self, value, state=None):
        return value

    def resources(self):
        for r in super(ProjectUserSelect, self).resources(): yield r
        yield ew.CSSLink('css/autocomplete.css')
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

class AttachmentList(ew_core.Widget):
    template='jinja:allura:templates/widgets/attachment_list.html'
    defaults=dict(
        ew_core.Widget.defaults,
        attachments=None,
        edit_mode=None)

class AttachmentAdd(ew_core.Widget):
    template='jinja:allura:templates/widgets/attachment_add.html'
    defaults=dict(
        ew_core.Widget.defaults,
        action=None,
        name=None)

    def resources(self):
        for r in super(AttachmentAdd, self).resources(): yield r
        yield onready('''
            $("input.attachment_form_add_button").click(function () {
                $(this).hide();
                $(".attachment_form_fields", this.parentNode).show();
            });
         ''')

class SubmitButton(ew.SubmitButton):
    attrs={'class':'ui-state-default ui-button ui-button-text'}

class AutoResizeTextarea(ew.TextArea):
    defaults=dict(
        ew.TextArea.defaults,
        name=None,
        value=None,
        css_class='auto_resize')

    def resources(self):
        yield ew.JSLink('js/jquery.elastic.js')
        yield onready('''
            $('textarea.auto_resize').elastic().focus(function(){
                $(this).keyup();
            });
        ''')

class MarkdownEdit(AutoResizeTextarea):
    template='jinja:allura:templates/widgets/markdown_edit.html'
    validator = fev.UnicodeString()
    defaults=dict(
        AutoResizeTextarea.defaults,
        name=None,
        value=None,
        show_label=True)

    def from_python(self, value, state=None):
        return value

    def resources(self):
        for r in super(MarkdownEdit, self).resources(): yield r
        yield ew.JSLink('js/jquery.lightbox_me.js')
        yield ew.JSLink('js/jquery.textarea.js')
        yield ew.JSLink('js/sf_markitup.js')
        yield ew.CSSLink('css/markitup_sf.css')

class PageList(ew_core.Widget):
    template='jinja:allura:templates/widgets/page_list.html'
    defaults=dict(
        ew_core.Widget.defaults,
        name=None,
        limit=None,
        count=0,
        page=0,
        show_label=False)

    def paginator(self, count, page, limit, zero_based_pages=True):
        page_offset = 1 if zero_based_pages else 0
        limit = 10 if limit is None else limit
        def page_url(page):
            params = request.GET.copy()
            params['page'] = page - page_offset
            return url(request.path, params)
        return paginate.Page(range(count), page + page_offset, int(limit),
        url=page_url)

    def resources(self):
        yield ew.CSSLink('css/page_list.css')

    @property
    def url_params(self, **kw):
        url_params = dict()
        for k,v in request.params.iteritems():
            if k not in ['limit','count','page']:
                url_params[k] = v
        return url_params

class PageSize(ew_core.Widget):
    template='jinja:allura:templates/widgets/page_size.html'
    defaults=dict(
        ew_core.Widget.defaults,
        limit=None,
        name=None,
        count=0,
        show_label=False)

    @property
    def url_params(self, **kw):
        url_params = dict()
        for k,v in request.params.iteritems():
            if k not in ['limit','count','page']:
                url_params[k] = v
        return url_params

    def resources(self):
        yield onready('''
            $('select.results_per_page').change(function () {
                this.form.submit();});''')

class FileChooser(ew.InputField):
    template='jinja:allura:templates/widgets/file_chooser.html'
    validator=fev.FieldStorageUploadConverter()
    defaults=dict(
        ew.InputField.defaults,
        name=None)

    def resources(self):
        for r in super(FileChooser, self).resources(): yield r
        yield ew.JSLink('js/jquery.file_chooser.js')
        yield onready('''
            var num_files = 0;
            var chooser = $('input.file_chooser').file();
            chooser.choose(function (e, input) {
                var holder = document.createElement('div');
                holder.style.clear = 'both';
                e.target.parentNode.appendChild(holder);
                $(holder).append(input.val());
                $(holder).append(input);
                input.attr('name', e.target.id + '-' + num_files);
                input.hide();
                ++num_files;
                var delete_link = document.createElement('a');
                delete_link.className = 'btn';
                var icon = document.createElement('b');
                icon.className = 'ico delete';
                delete_link.appendChild(icon);
                $(delete_link).click(function () {
                    this.parentNode.parentNode.removeChild(this.parentNode);
                });
                $(holder).append(delete_link);
            });''')

class JQueryMixin(object):
    js_widget_name = None
    js_plugin_file = None
    js_params = [
        'container_cls'
        ]
    container_cls = 'container'

    def resources(self):
        for r in super(JQueryMixin, self).resources():
            yield r
        if self.js_plugin_file is not None: yield self.js_plugin_file
        opts = dict(
            (k, getattr(self, k))
            for k in self.js_params )
        yield onready('''
$(document).bind('clone', function () {
    $('.%s').%s(%s); });
$(document).trigger('clone');
            ''' % (self.container_cls, self.js_widget_name, json.dumps(opts)));

class SortableRepeatedMixin(JQueryMixin):
    js_widget_name = 'SortableRepeatedField'
    js_plugin_file = ew.JSLink('js/sortable_repeated_field.js')
    js_params = JQueryMixin.js_params + [
        'field_cls',
        'flist_cls',
        'stub_cls',
        'msg_cls',
        ]
    defaults=dict(
        container_cls='sortable-repeated-field',
        field_cls='sortable-field',
        flist_cls='sortable-field-list',
        stub_cls='sortable-field-stub',
        msg_cls='sortable-field-message',
        empty_msg='No fields have been defined',
        nonempty_msg='Drag and drop the fields to reorder',
        repetitions=0)
    button =  ew.InputField(
        css_class='add', field_type='button', value='New Field')

class SortableRepeatedField(SortableRepeatedMixin, ew.RepeatedField):
    template='genshi:allura.templates.widgets.sortable_repeated_field'
    defaults=dict(
        ew.RepeatedField.defaults,
        **SortableRepeatedMixin.defaults)

class SortableTable(SortableRepeatedMixin, ew.TableField):
    template='genshi:allura.templates.widgets.sortable_table'
    defaults=dict(
        ew.TableField.defaults,
        **SortableRepeatedMixin.defaults)

class StateField(JQueryMixin, ew.CompoundField):
    template='genshi:allura.templates.widgets.state_field'
    js_widget_name = 'StateField'
    js_plugin_file = ew.JSLink('js/state_field.js')
    js_params = JQueryMixin.js_params + [
        'selector_cls',
        'field_cls',
        ]
    defaults=dict(
        ew.CompoundField.defaults,
        js_params = js_params,
        container_cls='state-field-container',
        selector_cls='state-field-selector',
        field_cls='state-field',
        show_label=False,
        selector = None,
        states = {},
        )

    @property
    def fields(self):
        return [self.selector] + self.states.values()

class DateField(JQueryMixin, ew.TextField):
    js_widget_name = 'datepicker'
    js_params = JQueryMixin.js_params
    container_cls = 'ui-date-field'
    defaults=dict(
        ew.TextField.defaults,
        container_cls = 'ui-date-field',
        css_class = 'ui-date-field')

    def resources(self):
        for r in super(DateField, self).resources(): yield r
        yield ew.CSSLink('css/jquery.ui.datepicker.css')

class FieldCluster(ew.CompoundField):
    template='genshi:allura.templates.widgets.field_cluster'

class AdminField(ew.InputField):
    '''Field with the correct layout/etc for an admin page'''
    template='jinja:allura:templates/widgets/admin_field.html'
    defaults=dict(
        ew.InputField.defaults,
        field=None,
        css_class=None,
        errors=None)

    def __init__(self, **kw):
        super(AdminField, self).__init__(**kw)
        for p in self.field.get_params():
            setattr(self, p, getattr(self.field, p))

    def resources(self):
        for r in self.field.resources():
            yield r

class Lightbox(ew_core.Widget):
    template='jinja:allura:templates/widgets/lightbox.html'
    defaults=dict(
        name=None,
        trigger=None,
        content='')

    def resources(self):
        yield ew.JSLink('js/jquery.lightbox_me.js')
        yield onready('''
            var $lightbox = $('#lightbox_%s');
            var $trigger = $('%s');
            $trigger.bind('click', function(e) {
                $lightbox.lightbox_me();
                return false;
            });
            $($lightbox).delegate('.close', 'click', function(e) {
                $lightbox.trigger('close');
                return false;
            });
        ''' % (self.name, self.trigger))
