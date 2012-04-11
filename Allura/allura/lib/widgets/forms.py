import logging
import warnings
from pylons import g
from allura.lib import validators as V
from allura.lib import helpers as h
from allura.lib import plugin
from allura.lib.widgets import form_fields as ffw
from allura import model as M

from formencode import validators as fev
import formencode

import ew as ew_core
import ew.jinja2_ew as ew

log = logging.getLogger(__name__)

class NeighborhoodProjectTakenValidator(fev.FancyValidator):

    def _to_python(self, value, state):
        value = h.really_unicode(value or '').encode('utf-8').lower()
        neighborhood = M.Neighborhood.query.get(name=state.full_dict['neighborhood'])
        message = plugin.ProjectRegistrationProvider.get().name_taken(value, neighborhood)
        if message:
            raise formencode.Invalid(message, value, state)
        return value

class ForgeForm(ew.SimpleForm):
    antispam=False
    template='jinja:allura:templates/widgets/forge_form.html'
    defaults=dict(
        ew.SimpleForm.defaults,
        submit_text='Save',
        style='standard',
        method='post',
        enctype=None)

    def display_label(self, field, label_text=None):
        ctx = super(ForgeForm, self).context_for(field)
        label_text = (
            label_text
            or ctx.get('label')
            or getattr(field, 'label', None)
            or ctx['name'])
        html = '<label for="%s">%s</label>' % (
            ctx['id'], label_text)
        return h.html.literal(html)

    def context_for(self, field):
        ctx = super(ForgeForm, self).context_for(field)
        if self.antispam:
            ctx['rendered_name'] = g.antispam.enc(ctx['name'])
        return ctx

    def display_field(self, field, ignore_errors=False):
        ctx = self.context_for(field)
        display = field.display(**ctx)
        if ctx['errors'] and field.show_errors and not ignore_errors:
            display = "%s<div class='error'>%s</div>" % (display, ctx['errors'])
        return h.html.literal(display)

    def display_field_by_idx(self, idx, ignore_errors=False):
        warnings.warn(
            'ForgeForm.display_field_by_idx is deprecated; use '
            'ForgeForm.display_field() instead', DeprecationWarning)
        field = self.fields[idx]
        ctx = self.context_for(field)
        display = field.display(**ctx)
        if ctx['errors'] and field.show_errors and not ignore_errors:
            display = "%s<div class='error'>%s</div>" % (display, ctx['errors'])
        return display

class PasswordChangeForm(ForgeForm):
    class fields(ew_core.NameList):
        oldpw = ew.PasswordField(
            label='Old Password', validator=fev.UnicodeString(not_empty=True))
        pw = ew.PasswordField(
            label='New Password',
            validator=fev.UnicodeString(not_empty=True, min=6))
        pw2 = ew.PasswordField(
            label='New Password (again)',
            validator=fev.UnicodeString(not_empty=True))

    @ew_core.core.validator
    def to_python(self, value, state):
        d = super(PasswordChangeForm, self).to_python(value, state)
        if d['pw'] != d['pw2']:
            raise formencode.Invalid('Passwords must match', value, state)
        return d

class UploadKeyForm(ForgeForm):
    class fields(ew_core.NameList):
        key = ew.TextArea(label='SSH Public Key')

class RegistrationForm(ForgeForm):
    class fields(ew_core.NameList):
        display_name = ew.TextField(
            label='Displayed Name',
            validator=fev.UnicodeString(not_empty=True))
        username = ew.TextField(
            label='Desired Username',
            validator=fev.Regex(
                h.re_path_portion))
        username.validator._messages['invalid'] = (
            'Usernames must include only letters, numbers, and dashes.'
            ' They must also start with a letter and be at least 3 characters'
            ' long.')
        pw = ew.PasswordField(
            label='New Password',
            validator=fev.UnicodeString(not_empty=True, min=8))
        pw2 = ew.PasswordField(
            label='New Password (again)',
            validator=fev.UnicodeString(not_empty=True))

    @ew_core.core.validator
    def to_python(self, value, state):
        d = super(RegistrationForm, self).to_python(value, state)
        value['username'] = username = value['username'].lower()
        if M.User.by_username(username):
            raise formencode.Invalid('That username is already taken. Please choose another.',
                                    value, state)
        if d['pw'] != d['pw2']:
            raise formencode.Invalid('Passwords must match', value, state)
        return d

class AdminForm(ForgeForm):
    template='jinja:allura:templates/widgets/admin_form.html'

class NeighborhoodOverviewForm(ForgeForm):
    template='jinja:allura:templates/widgets/neighborhood_overview_form.html'

    class fields(ew_core.NameList):
        name = ew.TextField()
        redirect = ew.TextField()
        homepage = ffw.AutoResizeTextarea()
        allow_browse = ew.Checkbox(label='')
        css = ffw.AutoResizeTextarea()
        project_template = ffw.AutoResizeTextarea(
                validator=V.JsonValidator(if_empty=''))
        icon = ew.FileField()
        tracking_id = ew.TextField()

    def from_python(self, value, state):
        if value.features['css'] == "picker":
            self.list_color_inputs = True
            self.color_inputs = value.get_css_for_picker()
        else:
            self.list_color_inputs = False
            self.color_inputs = []
        return super(NeighborhoodOverviewForm, self).from_python(value, state)

    def display_field(self, field, ignore_errors=False):
        if field.name == "css" and self.list_color_inputs:
            display = '<table class="table_class">'
            ctx = self.context_for(field)
            for inp in self.color_inputs:
                additional_inputs = inp.get('additional', '')
                empty_val = False
                if inp['value'] is None or inp['value'] == '':
                    empty_val = True
                display += '<tr><td class="left"><label>%(label)s</label></td>'\
                           '<td><input type="checkbox" name="%(ctx_name)s-%(inp_name)s-def" %(def_checked)s>default</td>'\
                           '<td class="right"><div class="%(ctx_name)s-%(inp_name)s-inp"><table class="input_inner">'\
                           '<tr><td><input type="text" class="%(inp_type)s" name="%(ctx_name)s-%(inp_name)s" '\
                           'value="%(inp_value)s"></td><td>%(inp_additional)s</td></tr></table></div></td></tr>\n' % {'ctx_id': ctx['id'],
                                                            'ctx_name': ctx['name'],
                                                            'inp_name': inp['name'],
                                                            'inp_value': inp['value'],
                                                            'label': inp['label'],
                                                            'inp_type': inp['type'],
                                                            'def_checked': 'checked="checked"' if empty_val else '',
                                                            'inp_additional': additional_inputs}
            display += '</table>'

            if ctx['errors'] and field.show_errors and not ignore_errors:
                display = "%s<div class='error'>%s</div>" % (display, ctx['errors'])

            return h.html.literal(display)
        else:
            return super(NeighborhoodOverviewForm, self).display_field(field, ignore_errors)

    @ew_core.core.validator
    def to_python(self, value, state):
        d = super(NeighborhoodOverviewForm, self).to_python(value, state)
        neighborhood = M.Neighborhood.query.get(name=d.get('name', None))
        if neighborhood and neighborhood.features['css'] == "picker":
            css_form_dict = {}
            for key in value.keys():
                def_key = "%s-def" % (key)
                if key[:4] == "css-" and def_key not in value:
                    css_form_dict[key[4:]] = value[key]
            d['css'] = M.Neighborhood.compile_css_for_picker(css_form_dict)
        return d

    def resources(self):
        for r in super(NeighborhoodOverviewForm, self).resources(): yield r
        yield ew.CSSLink('css/colorPicker.css')
        yield ew.CSSLink('css/jqfontselector.css')
        yield ew.CSSScript('''
table.table_class, table.input_inner{
  margin: 0;
  padding: 0;
  width: 99%;
}

table.table_class .left{ text-align: left; }
table.table_class .right{ text-align: right; width: 50%;}
table.table_class tbody tr td { border: none; }
table.table_class select.add_opt {width: 5em; margin:0; padding: 0;}
        ''')
        yield ew.JSLink('js/jquery.colorPicker.js')
        yield ew.JSLink('js/jqfontselector.js')
        yield ew.JSScript('''
            $(function(){
              $('.table_class').find('input[type="checkbox"]').each(function(index, element) {
                var cb_name = $(this).attr('name');
                var inp_name = cb_name.substr(0, cb_name.length-4);
                var inp_el = $('div[class="'+inp_name+'-inp"]');

                if ($(this).attr('checked')) {
                  inp_el.hide();
                }

                $(element).click(function(e) {
                  if ($(this).attr('checked')) {
                    inp_el.hide();
                  } else {
                    inp_el.show();
                  }
                });
              });

              $('.table_class').find('input.color').each(function(index, element) {
                $(element).colorPicker();
              });
              $('.table_class').find('input.font').each(function(index, element) {
                $(element).fontSelector();
              });
            });
        ''')

class NeighborhoodAddProjectForm(ForgeForm):
    template='jinja:allura:templates/widgets/neighborhood_add_project.html'
    antispam=True
    defaults=dict(
        ForgeForm.defaults,
        method='post',
        submit_text='Start',
        neighborhood=None)

    class fields(ew_core.NameList):
        project_description = ew.HiddenField(label='Public Description')
        neighborhood = ew.HiddenField(label='Neighborhood')
        private_project = ew.Checkbox(label="", attrs={'class':'unlabeled'})
        project_name = ew.InputField(label='Project Name', field_type='text',
            validator=formencode.All(
                fev.UnicodeString(not_empty=True, max=40),
                V.MaxBytesValidator(max=40)))
        project_unixname = ew.InputField(
            label='Short Name', field_type='text',
            validator=formencode.All(
                fev.String(not_empty=True),
                fev.MinLength(3),
                fev.MaxLength(15),
                fev.Regex(
                    r'^[A-z][-A-z0-9]{2,}$',
                    messages={'invalid':'Please use only letters, numbers, and dashes 3-15 characters long.'}),
                NeighborhoodProjectTakenValidator()))

        tools = ew.CheckboxSet(name='tools', options=[
            ew.Option(label='Wiki', html_value='Wiki', selected=True),
            ew.Option(label='Git', html_value='Git', selected=True),
            ew.Option(label='Hg', html_value='Hg'),
            ew.Option(label='SVN', html_value='SVN'),
            ew.Option(label='Tickets', html_value='Tickets', selected=True),
            ew.Option(label='Downloads', html_value='Downloads', selected=True),
            ew.Option(label='Discussion', html_value='Discussion', selected=True),
            ew.Option(label='Blog', html_value='Blog')
        ])

    def resources(self):
        for r in super(NeighborhoodAddProjectForm, self).resources(): yield r
        yield ew.CSSLink('css/add_project.css')
        project_name = g.antispam.enc('project_name')
        project_unixname = g.antispam.enc('project_unixname')

        yield ew.JSScript('''
            $(function(){
                var $scms = $('input[type=checkbox].scm');
                var $name_avail_message = $('#name_availability');
                var $name_input = $('input[name="%(project_name)s"]');
                var $unixname_input = $('input[name="%(project_unixname)s"]');
                var $url_fragment = $('#url_fragment');
                var $error_icon = $('#error_icon');
                var $success_icon = $('#success_icon');
                var delay = (function(){
                  var timer = 0;
                  return function(callback, ms){
                    clearTimeout (timer);
                    timer = setTimeout(callback, ms);
                  };
                })();
                $name_input.focus();
                var handle_name_taken = function(message){
                    if(message){
                        $success_icon.hide();
                        $error_icon.show();
                        $name_avail_message.html(message);
                        $name_avail_message.removeClass('success');
                        $name_avail_message.addClass('error');
                    }
                    else{
                        $error_icon.hide();
                        $success_icon.show();
                        $name_avail_message.html('This name is available.');
                        $name_avail_message.removeClass('error');
                        $name_avail_message.addClass('success');
                    }
                    $('div.error').hide();
                    $name_avail_message.show();
                };
                $scms.change(function(){
                    if ( $(this).attr('checked') ) {
                        var on = this;
                        $scms.each(function(){
                            if ( this !== on ) {
                                $(this).removeAttr('checked');
                            }
                        });
                    }
                });
                $name_input.blur(function(){
                    if ($unixname_input.val() === "" || $name_avail_message.hasClass('error')) {
                        $.getJSON('suggest_name',{'project_name':$name_input.val()},function(result){
                            $unixname_input.val(result.suggested_name);
                            $url_fragment.html(result.suggested_name);
                            handle_name_taken(result.message);
                        });
                    }
                });
                $unixname_input.keyup(function(){
                    $url_fragment.html($unixname_input.val());
                    delay(function(){
                        $.getJSON('check_name',{'project_name':$unixname_input.val()},function(result){
                            handle_name_taken(result.message);
                        });
                    }, 500 );
                });
            });
        ''' % dict(project_name=project_name, project_unixname=project_unixname))
