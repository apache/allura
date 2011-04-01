import logging
import re
import  ming.orm.ormsession
from pylons import g
from allura.lib import helpers as h
from allura.lib import exceptions as forge_exc
from allura.lib import plugin
from allura import model as M

from formencode import validators as fev
import formencode

import ew as ew_core
import ew.jinja2_ew as ew

log = logging.getLogger(__name__)

class ForgeForm(ew.SimpleForm):
    antispam=False
    template='jinja:allura:templates/widgets/forge_form.html'
    defaults=dict(
        ew.SimpleForm.defaults,
        submit_text='Save',
        style='standard',
        method='post',
        enctype=None)

    def context_for(self, field):
        ctx = super(ForgeForm, self).context_for(field)
        if self.antispam:
            ctx['rendered_name'] = g.antispam.enc(ctx['name'])
        return ctx

    def display_field_by_idx(self, idx, ignore_errors=False):
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

    @property
    def fields(self):
        fields = [
            ew.InputField(name='project_name', label='Project Name', field_type='text'),
            ew.InputField(name='project_unixname', label='Short Name', field_type='text',
                          validator=formencode.All(
                            fev.String(not_empty=True),
                            fev.MinLength(3),
                            fev.MaxLength(15),
                            fev.Regex(r'^[A-z][-A-z0-9]{2,}$', messages={'invalid':'Please use only letters, numbers, and dashes 3-15 characters long.'}),
                            NeighborhoodProjectTakenValidator())),
            ew.HiddenField(name='project_description', label='Public Description'),
            ew.HiddenField(name='neighborhood', label='Neighborhood'),
            ew.Checkbox(name="Wiki", label="", attrs={'class':'unlabeled'}),
            ew.Checkbox(name="Git", label="", attrs={'class':'labeled'}),
            ew.Checkbox(name="Hg", label="", attrs={'class':'labeled'}),
            ew.Checkbox(name="SVN", label="", attrs={'class':'labeled'}),
            ew.Checkbox(name="Tickets", label="", attrs={'class':'unlabeled'}),
            ew.Checkbox(name="Downloads", label="", attrs={'class':'unlabeled'}),
            # ew.Checkbox(name="Stats", label="", attrs={'class':'unlabeled'}),
            ew.Checkbox(name="Discussion", label="", attrs={'class':'unlabeled'})
        ]
        return fields

    def resources(self):
        for r in super(NeighborhoodAddProjectForm, self).resources(): yield r
        yield ew.CSSLink('css/add_project.css')
        project_name = g.antispam.enc('project_name')
        project_unixname = g.antispam.enc('project_unixname')

        yield ew.JSScript('''
            $(function(){
                var $scms = $('[name=Git],[name=Hg],[name=SVN]');
                var $suggest_btn = $('#suggest_project_name');
                var $name_avail_message = $('#name_availablity');
                var $name_input = $('input[name="%(project_name)s"]');
                var $unixname_input = $('input[name="%(project_unixname)s"]');
                var handle_name_taken = function(message){
                    if(message){
                        $name_avail_message.html(message);
                        $name_avail_message.removeClass('success');
                        $name_avail_message.addClass('error');
                    }
                    else{
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
                $suggest_btn.click(function(){
                    $.getJSON('suggest_name',{'project_name':$name_input.val()},function(result){
                        $unixname_input.val(result.suggested_name);
                        handle_name_taken(result.message);
                    });
                });
                $unixname_input.change(function(){
                    $.getJSON('check_name',{'project_name':$unixname_input.val()},function(result){
                        handle_name_taken(result.message);
                    });
                });
            });
        ''' % dict(project_name=project_name, project_unixname=project_unixname))


class NeighborhoodProjectTakenValidator(fev.FancyValidator):

    def _to_python(self, value, state):
        value = h.really_unicode(value or '').encode('utf-8').lower()
        message = plugin.ProjectRegistrationProvider.get().name_taken(value)
        if message:
            raise formencode.Invalid(message, value, state)
        return value

