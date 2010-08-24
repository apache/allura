from pylons import c
from tg import request
from urllib import urlencode
import json

from formencode import validators as fev
import ew

def onready(text):
    return ew.JSScript('$(document).ready(function(){%s});' % text);

class MarkdownEdit(ew.InputField):
    template='genshi:allura.lib.widgets.templates.markdown_edit'
    validator = fev.UnicodeString()
    params=['name','value','show_label']
    show_label=True
    name=None
    value=None

    def resources(self):
        yield ew.resource.JSLink('js/jquery.markitup.pack.js')
        yield ew.resource.JSLink('js/jquery.markitup.markdown.js')
        yield ew.resource.JSLink('js/sf_markitup.js')
        yield ew.resource.CSSLink('css/markitup.css', compress=False)
        yield ew.resource.CSSLink('css/markitup_markdown.css', compress=False)
        yield ew.resource.CSSLink('css/markitup_sf.css')
        yield onready('''
              markdownSettings.previewParserPath = "/nf/markdown_to_html?project=%s"+
                "&app=%s";
        ''' % (c.project and c.project.shortname or '', (c.project and c.app) and c.app.config.options['mount_point'] or ''))

class UserTagEdit(ew.InputField):
    template='genshi:allura.lib.widgets.templates.user_tag_edit'
    validator = fev.UnicodeString()
    params=['name','user_tags', 'className', 'show_label']
    show_label=True
    name=None
    user_tags=None
    className=''

    def resources(self):
        yield ew.resource.JSLink('js/jquery.tag.editor.js')
        yield onready('''
          $('input.user_tag_edit').tagEditor({
            confirmRemoval: false,
            completeOnSeparator: true,
            completeOnBlur: true
          });
        ''');

class LabelEdit(ew.InputField):
    template='genshi:allura.lib.widgets.templates.label_edit'
    validator = fev.UnicodeString()
    params=['name', 'className', 'show_label', 'value']
    show_label=True
    name=None
    value=None
    className=''

    def resources(self):
        yield ew.resource.JSLink('js/jquery.tag.editor.js')
        yield onready('''
          $('input.label_edit').tagEditor({
            confirmRemoval: false,
            completeOnSeparator: true,
            completeOnBlur: true
          });
        ''')

class ProjectUserSelect(ew.InputField):
    template='genshi:allura.lib.widgets.templates.project_user_select'
    params=['name', 'value', 'show_label', 'className']
    show_label=True
    name=None
    value=None
    className=None

    def __init__(self, **kw):
      if not isinstance(self.value, list):
          self.value=[self.value]
      super(ProjectUserSelect, self).__init__(**kw)

    def resources(self):
        for r in super(ProjectUserSelect, self).resources(): yield r
        yield ew.resource.CSSLink('css/autocomplete.css')
        yield onready('''
          $('input.project_user_select').autocomplete({
            source: function(request, response) {
              $.ajax({
                url: "%suser_search",
                dataType: "json",
                data: {
                  term: request.term
                },
                success: function(data) {
                  response(data.users);
                }
              });
            },
            minLength: 2
          });''' % c.project.url())

class AttachmentList(ew.Widget):
    template='genshi:allura.lib.widgets.templates.attachment_list'
    params=['attachments','edit_mode']
    attachments=None
    edit_mode=None

class AttachmentAdd(ew.Widget):
    template='genshi:allura.lib.widgets.templates.attachment_add'
    params=['action','name']
    action=None
    name=None

    def resources(self):
        for r in super(AttachmentAdd, self).resources(): yield r
        yield onready('''
            $("input.attachment_form_add_button").click(function(){
                $(this).hide();
                $(".attachment_form_fields", this.parentNode).show();
            });
         ''')

class SubmitButton(ew.SubmitButton):
    attrs={'class':'ui-state-default ui-button ui-button-text'}

class AutoResizeTextarea(ew.TextArea):
    params=['name', 'value']
    name=None
    value=None
    css_class="auto_resize"

    def resources(self):
        yield ew.resource.JSLink('js/jquery.autoresize.min.js')
        yield onready('''
            $('textarea.auto_resize').autoResize({
                // On resize:
                onResize : function() {
                    $(this).css({opacity:0.8});
                },
                // After resize:
                animateCallback : function() {
                    $(this).css({opacity:1});
                },
                // Quite slow animation:
                animateDuration : 300,
                // More extra space:
                extraSpace : 0
            });
        ''')

class PageList(ew.Widget):
    template='genshi:allura.lib.widgets.templates.page_list'
    params=['limit','count','page', 'url_params']
    show_label=False
    name=None
    limit=None
    count=0
    page=0
    
    @property
    def url_params(self, **kw):
        url_params = dict()
        for k,v in request.params.iteritems():
            if k not in ['limit','count','page']:
                url_params[k] = v
        return url_params

class PageSize(ew.Widget):
    template='genshi:allura.lib.widgets.templates.page_size'
    params=['limit','url_params']
    show_label=False
    name=None
    limit=None
    
    @property
    def url_params(self, **kw):
        url_params = dict()
        for k,v in request.params.iteritems():
            if k not in ['limit','count','page']:
                url_params[k] = v
        return url_params

    def resources(self):
        yield onready('''
            $('select.results_per_page').change(function(){
                this.form.submit();})''')

class FileChooser(ew.InputField):
    template='genshi:allura.lib.widgets.templates.file_chooser'
    params=['name']
    name=None
    validator=fev.FieldStorageUploadConverter()

    def resources(self):
        for r in super(FileChooser, self).resources(): yield r
        yield ew.resource.JSLink('js/jquery.file_chooser.js')
        yield onready('''
            var num_files = 0;
            var chooser = $('input.file_chooser').file();
            chooser.choose(function(e, input) {
                var holder = document.createElement('div');
                holder.style.clear = 'both';
                e.target.parentNode.appendChild(holder);
                $(holder).append(input.val());
                $(holder).append(input);
                input.attr('name', e.target.id + '-' + num_files);
                input.hide();
                ++num_files;
                var delete_link = document.createElement('a');
                delete_link.className = 'btn ico';
                var icon = document.createElement('b');
                icon.className = 'ui-icon ui-icon-close';
                delete_link.appendChild(icon);
                $(delete_link).click(function(){
                    this.parentNode.parentNode.removeChild(this.parentNode);
                });
                $(holder).append(delete_link);
            });''')
