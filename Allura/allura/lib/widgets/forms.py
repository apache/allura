import logging
import warnings
from pylons import g
from allura.lib import validators as V
from allura.lib import helpers as h
from allura.lib import plugin
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
                });
                $unixname_input.change(function(){
                    $url_fragment.html($unixname_input.val());
                    $.getJSON('check_name',{'project_name':$unixname_input.val()},function(result){
                        handle_name_taken(result.message);
                    });
                });
            });
        ''' % dict(project_name=project_name, project_unixname=project_unixname))
