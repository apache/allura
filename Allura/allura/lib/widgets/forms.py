import logging
import  ming.orm.ormsession
from allura.lib import helpers as h
from allura.lib import exceptions as forge_exc
from allura import model as M

from formencode import validators as fev
import formencode

import ew as ew_core
import ew.jinja2_ew as ew

log = logging.getLogger(__name__)

class ForgeForm(ew.SimpleForm):
    template='jinja:widgets/forge_form.html'
    defaults=dict(
        ew.SimpleForm.defaults,
        submit_text='Save',
        enctype=None)

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
        display_name = ew.TextField(label='Displayed Name')
        username = ew.TextField(
            label='Desired Username',
            validator=fev.Regex(
                h.re_path_portion))
        username.validator._messages['invalid'] = (
            'Usernames must include only letters, numbers, and dashes,'
            ' and must start with a letter and be at least 3 characters'
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
    template='jinja:widgets/admin_form.html'

class NeighborhoodAddProjectForm(ForgeForm):
    template='jinja:widgets/neighborhood_add_project.html'
    defaults=dict(
        ForgeForm.defaults,
        submit_text='Start')

    @property
    def fields(self):
        fields = [
            ew.InputField(name='project_unixname', label='', field_type='text',
                          validator=formencode.All(
                            fev.String(not_empty=True),
                            fev.Regex(r'^[A-z][-A-z0-9]{2,}$', messages={'invalid':'Please use only letters, numbers, and dash characters.'}),
                            NeighborhoodAddProjectValidator())),
            ew.HiddenField(name='project_name', label='Project Name'),
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


class NeighborhoodAddProjectValidator(fev.FancyValidator):

    def _to_python(self, value, state):
        try:
            value = h.really_unicode(value or '').encode('utf-8').lower()
            neighborhood = M.Neighborhood.query.get(name=state.full_dict['neighborhood'])
            neighborhood.register_project(value)
            return value
        except forge_exc.ProjectConflict:
            ming.orm.ormsession.ThreadLocalORMSession.close_all()
            raise formencode.Invalid('A project already exists with that name, please choose another.',
                                     value, state)
        except Exception, ex:
            log.exception('Unexpected error creating project')
            ming.orm.ormsession.ThreadLocalORMSession.close_all()
            raise formencode.Invalid(str(ex), value, state)

