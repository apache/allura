from pylons import c
from formencode import validators as fev

import ew

class MarkdownEdit(ew.InputField):
    template='genshi:pyforge.lib.widgets.templates.markdown_edit'
    validator = fev.UnicodeString()
    params=['name','value','show_label']
    show_label=True
    name=None
    value=None

    def resources(self):
        yield ew.resource.JSLink('js/jquery.markitup.pack.js', compress=False)
        yield ew.resource.JSLink('js/jquery.markitup.markdown.js')
        yield ew.resource.JSLink('js/sf_markitup.js')
        yield ew.resource.CSSLink('css/markitup.css', compress=False)
        yield ew.resource.CSSLink('css/markitup_markdown.css', compress=False)
        yield ew.resource.CSSLink('css/markitup_sf.css')
        yield ew.JSScript('''
          $(window).load(function() {
              markdownSettings.previewParserPath = "/nf/markdown_to_html?project=%s"+
                "&app=%s";
          });
        ''' % (c.project and c.project.shortname or '', (c.project and c.app) and c.app.config.options['mount_point'] or ''))

class UserTagEdit(ew.InputField):
    template='genshi:pyforge.lib.widgets.templates.user_tag_edit'
    validator = fev.UnicodeString()
    params=['name','user_tags', 'className', 'show_label']
    show_label=True
    name=None
    user_tags=None
    className=''

    def resources(self):
        yield ew.resource.JSLink('js/jquery.tag.editor.js')
        yield ew.JSScript('''
        $(window).load(function(){
          $('input.user_tag_edit').tagEditor({
            confirmRemoval: false,
            completeOnSeparator: true,
            completeOnBlur: true
          });
        });
        ''')

class LabelEdit(ew.InputField):
    template='genshi:pyforge.lib.widgets.templates.label_edit'
    validator = fev.UnicodeString()
    params=['name', 'className', 'show_label', 'value']
    show_label=True
    name=None
    value=None
    className=''

    def resources(self):
        yield ew.resource.JSLink('js/jquery.tag.editor.js')
        yield ew.JSScript('''
        $(window).load(function(){
          $('input.label_edit').tagEditor({
            confirmRemoval: false,
            completeOnSeparator: true,
            completeOnBlur: true
          });
        });
        ''')

class ProjectUserSelect(ew.InputField):
    template='genshi:pyforge.lib.widgets.templates.project_user_select'
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
        yield ew.JSScript('''
        $(window).load(function(){
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
          });
        });''' % c.project.url())

class AttachmentList(ew.Widget):
    template='genshi:pyforge.lib.widgets.templates.attachment_list'
    params=['attachments','edit_mode']
    attachments=None
    edit_mode=None

class AttachmentAdd(ew.Widget):
    template='genshi:pyforge.lib.widgets.templates.attachment_add'
    params=['action','name']
    action=None
    name=None

    def resources(self):
        for r in super(AttachmentAdd, self).resources(): yield r
        yield ew.JSScript('''
        $(window).load(function(){
            $("input.attachment_form_add_button").click(function(){
                $(this).hide();
                $(".attachment_form_fields", this.parentNode).show();
            });
        });''')

class SubmitButton(ew.SubmitButton):
    attrs={'class':'ui-state-default ui-button ui-button-text'}

class AutoResizeTextarea(ew.TextArea):
    params=['name', 'value']
    name=None
    value=None
    css_class="auto_resize"

    def resources(self):
        yield ew.resource.JSLink('js/jquery.autoresize.min.js')
        yield ew.JSScript('''
        $(window).load(function(){
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
        });''')

class PageList(ew.Widget):
    template='genshi:pyforge.lib.widgets.templates.page_list'
    params=['limit','count','page']
    show_label=False
    name=None
    limit=None
    count=0
    page=0

class PageSize(ew.Widget):
    template='genshi:pyforge.lib.widgets.templates.page_size'
    params=['limit']
    show_label=False
    name=None
    limit=None

    def resources(self):
        yield ew.JSScript('''
        $('select.results_per_page').change(function(){
            location.href=location.pathname+'?limit='+this.value;
        });
        ''')