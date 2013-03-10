import logging
import warnings
from pylons import g, c
from allura.lib import validators as V
from allura.lib import helpers as h
from allura.lib import plugin
from allura.lib.widgets import form_fields as ffw
from allura.lib.widgets.forms import ForgeForm
from allura import model as M

from formencode import validators as fev
import formencode
from forgeorganization.organization.model import WorkFields
import ew as ew_core
import ew.jinja2_ew as ew

from pytz import common_timezones, country_timezones, country_names

log = logging.getLogger(__name__)

class RegistrationForm(ForgeForm):
    class fields(ew_core.NameList):
        fullname = ew.TextField(
            label='Organization Full Name',
            validator=fev.UnicodeString(not_empty=True))
        shortname = ew.TextField(
            label='Desired Short Name',
            validator=formencode.All(
                fev.Regex(h.re_path_portion),
                fev.UnicodeString(not_empty=True)))
        orgtype = ew.SingleSelectField(
            label='Organization Type',
            options = [
                ew.Option(
                    py_value='For-profit business', 
                    label='For-profit business'),
                ew.Option(
                    py_value='Foundation or other non-profit organization',
                    label='Foundation or other non-profit organization'),
                ew.Option(
                    py_value='Research and/or education institution',
                    label='Research and/or education institution')],
            validator=fev.UnicodeString(not_empty=True))
        role = ew.TextField(
            label='Your Role',
            validator=fev.UnicodeString(not_empty=True))

class SearchForm(ForgeForm):
    defaults=dict(ForgeForm.defaults, submit_text='Search')

    class fields(ew_core.NameList):
        orgname = ew.TextField(
            label='Organization name', 
            validator=fev.UnicodeString(not_empty=True))

class RequestAdmissionForm(ForgeForm):
    defaults=dict(ForgeForm.defaults)

    class fields(ew_core.NameList):
        role = ew.TextField(
            label='Your role', 
            validator=fev.UnicodeString(not_empty=True))

class RequestCollaborationForm(ForgeForm):
    defaults=dict(ForgeForm.defaults)

    class fields(ew_core.NameList):
        project_url_name = ew.TextField(
            label='Project URL Name', 
            validator=fev.UnicodeString(not_empty=True))
        collaboration_type=ew.SingleSelectField(
            label='Collaboration Type', 
            options = [
                ew.Option(py_value='cooperation', label='Cooperation'),
                ew.Option(py_value='participation', label='Participation')])

class UpdateProfile(ForgeForm):
    defaults=dict(ForgeForm.defaults)

    class fields(ew_core.NameList):
        fullname=ew.TextField(
            label='Organization Full Name',
            validator=fev.UnicodeString(not_empty=True))
        organization_type=ew.SingleSelectField(
            label='Organization Type', 
            options = [
                ew.Option(
                    py_value='For-profit business', 
                    label='For-profit business'),
                ew.Option(
                    py_value='Foundation or other non-profit organization',
                    label='Foundation or other non-profit organization'),
                ew.Option(
                    py_value='Research and/or education institution',
                    label='Research and/or education institution')],
             validator=fev.UnicodeString(not_empty=True))
        description=ew.TextField(
            label='Description')
        dimension=ew.SingleSelectField(
            label='Dimension', 
            options = [
                ew.Option(
                    py_value='Small', 
                    label='Small organization (up to 50 members)'),
                ew.Option(
                    py_value='Medium',
                    label='Medium-size organization (51-250 members)'),
                ew.Option(
                    py_value='Large',
                    label='Big organization (at least 251 members)'),
                ew.Option(
                    py_value='Unknown',
                    label='Unknown')],
            validator=fev.UnicodeString(not_empty=True))
        headquarters=ew.TextField(
            label='Headquarters')
        website=ew.TextField(
            label='Website')

    def display(self, **kw):
        organization = kw.get('organization')
        self.fields['fullname'].attrs = dict(value=organization.fullname)
        self.fields['description'].attrs = dict(value=organization.description)
        for opt in self.fields['organization_type'].options:
            if opt.py_value == organization.organization_type:
                opt.selected = True
            else:
                opt.selected = False
        for opt in self.fields['dimension'].options:
            if opt.py_value == organization.dimension:
                opt.selected = True
            else:
                opt.selected = False
        self.fields['website'].attrs = dict(value=organization.website)
        self.fields['headquarters'].attrs = \
            dict(value=organization.headquarters)

        return super(UpdateProfile, self).display(**kw)

class InviteUser(ForgeForm):
    defaults=dict(ForgeForm.defaults)

    class fields(ew_core.NameList):
        username=ew.TextField(
            label='Username',
            validator=fev.UnicodeString(not_empty=True))
        role=ew.TextField(
            label='Role',
            validator=fev.UnicodeString(not_empty=True))
        
class AddWorkField(ForgeForm):
    defaults=dict(ForgeForm.defaults)

    def display(self, **kw):
        self.fields = [
            ew.SingleSelectField(
                name='workfield',
                label='Work Field',
                options = [ew.Option(py_value=wf._id, label=wf.name)
                           for wf in WorkFields.query.find()],
                validator=fev.UnicodeString(not_empty=True))]
        return super(AddWorkField, self).display(**kw)


    def to_python(self, value, state):
        d = super(AddWorkField, self).to_python(value, state)
        return d

class RemoveWorkField(ForgeForm):
    defaults=dict(ForgeForm.defaults, submit_text=None, show_errors=False)

    def display(self, **kw):
        wf = kw.get('workfield')

        self.fields = [
            ew.RowField(
                show_errors=False,
                hidden_fields=[
                    ew.HiddenField(
                        name="workfieldid",
                        attrs={'value':str(wf._id)},
                        show_errors=False)
                ],
                fields=[
                    ew.HTMLField(
                        text=wf.name,
                        show_errors=False),
                    ew.HTMLField(
                        text=wf.description,
                        show_errors=False),
                    ew.SubmitButton(
                        show_label=False,
                        attrs={'value':'Remove'},
                        show_errors=False)])]
        return super(RemoveWorkField, self).display(**kw)

    def to_python(self, value, state):
        d = {}
        d['workfield'] = WorkFields.getById(value['workfieldid'])
        return d

class ChangeMembershipFromUser(ForgeForm):
    defaults=dict(ForgeForm.defaults, submit_text=None, show_errors=False)

    def display(self, **kw):
        m = kw.get('membership')
        org = m.organization

        orgnamefield = '<a href="%s">%s</a>' % (org.url()+"organizationprofile", org.fullname)
        if c.user.username in m.organization.project().admins():
            orgnamefield+=' (<a href="%sadmin/organizationprofile">edit</a>)'%org.url()
        if m.status == 'active':
            statusoptions = [
                ew.Option(py_value='active',label='Active',selected=True),
                ew.Option(py_value='closed',label='Closed',selected=False)]
        elif m.status == 'closed':
            statusoptions = [
                ew.Option(py_value='closed',label='Closed',selected=True)]
        elif m.status == 'invitation':
            statusoptions = [
                ew.Option(
                    py_value='invitation',
                    label='Pending invitation',
                    selected=True),
                ew.Option(py_value='active',label='Accept',selected=False),
                ew.Option(py_value='remove',label='Decline',selected=False)]
        elif m.status == 'request':
            statusoptions = [
                ew.Option(
                    py_value='request',label='Pending request',selected=True),
                ew.Option(
                    py_value='remove',label='Remove request',selected=False)]
 
        self.fields = [
            ew.RowField(
                show_errors=False,
                hidden_fields=[
                    ew.HiddenField(
                        name="membershipid",
                        attrs={'value':str(m._id)},
                        show_errors=False),
                    ew.HiddenField(
                        name="requestfrom",
                        attrs={'value':'user'},
                        show_errors=False)
                ],
                fields=[
                    ew.HTMLField(
                        text=orgnamefield,
                        show_errors=False),
                    ew.HTMLField(
                        text=org.organization_type,
                        show_errors=False),
                    ew.TextField(
                        name='role',
                        attrs=dict(value=m.role),
                        show_errors=False),
                    ew.SingleSelectField(
                        name='status',
                        show_errors=False,
                        options = statusoptions),
                    ew.SubmitButton(
                        show_label=False,
                        attrs={'value':'Save'},
                        show_errors=False)])]
        return super(ChangeMembershipFromUser, self).display(**kw)

class ChangeMembershipFromOrganization(ForgeForm):
    defaults=dict(ForgeForm.defaults, submit_text=None, show_errors=False)

    def display(self, **kw):
        m = kw.get('membership')
        user = m.member

        if m.status == 'active':
            statusoptions = [
                ew.Option(py_value='active',label='Active',selected=True),
                ew.Option(py_value='closed',label='Closed',selected=False)]
        elif m.status == 'closed':
            statusoptions = [
                ew.Option(py_value='closed',label='Closed',selected=True)]
        elif m.status == 'invitation':
            statusoptions = [
                ew.Option(
                    py_value='invitation',
                    label='Pending invitation',
                    selected=True),
                ew.Option(
                    py_value='remove',
                    label='Remove invitation',
                    selected=False)]
        elif m.status == 'request':
            statusoptions = [
                ew.Option(
                    py_value='request',label='Pending request',selected=True),
                ew.Option(py_value='active',label='Accept',selected=False),
                ew.Option(py_value='remove',label='Decline',selected=False)]
 
        self.fields = [
            ew.RowField(
                show_errors=False,
                hidden_fields=[
                    ew.HiddenField(
                        name="membershipid",
                        attrs={'value':str(m._id)},
                        show_errors=False),
                    ew.HiddenField(
                        name="requestfrom",
                        attrs={'value':'organization'},
                        show_errors=False)
                ],
                fields=[
                    ew.HTMLField(
                        text='<a href="%s">%s</a>' % (
                            user.url(), user.display_name),
                        show_errors=False),
                    ew.TextField(
                        name='role',
                        attrs=dict(value=m.role),
                        show_errors=False),
                    ew.SingleSelectField(
                        name='status',
                        show_errors=False,
                        options = statusoptions),
                    ew.SubmitButton(
                        show_label=False,
                        attrs={'value':'Save'},
                        show_errors=False)])]
        return super(ChangeMembershipFromOrganization, self).display(**kw)

class ChangeCollaborationStatusForm(ForgeForm):
    defaults=dict(ForgeForm.defaults, submit_text=None, show_errors=False)

    def display(self, **kw):
        coll = kw.get('collaboration')
        proj = coll.project
        projfield = '<a href="%s">%s</a>' % (proj.url(), proj.name)
        
        select_cooperation = (coll.collaborationtype=='cooperation')
        if coll.status=='closed':
            options=[ew.Option(py_value='closed',label='Closed',selected=True)]
        elif coll.status=='active':
            options=[
                ew.Option(py_value='closed',label='Closed',selected=False),
                ew.Option(py_value='active',label='Active',selected=True)]
        elif coll.status=='invitation':
            options=[
                ew.Option(
                    py_value='invitation',
                    label='Pending invitation',
                    selected=True),
                ew.Option(
                    py_value='active',
                    label='Accept invitation',
                    selected=False),
                ew.Option(
                    py_value='remove',
                    label='Remove invitation',
                    selected=False)]
        elif coll.status=='request':
            options=[
                ew.Option(
                    py_value='request',
                    label='Pending request',
                    selected=True),
                ew.Option(
                    py_value='remove',
                    label='Remove request',
                    selected=False)]
        self.fields = [
            ew.RowField(
                show_errors=False,
                hidden_fields=[
                    ew.HiddenField(
                        name="collaborationid",
                        attrs={'value':str(coll._id)},
                        show_errors=False)
                ],
                fields=[
                    ew.HTMLField(
                        text=projfield,
                        show_errors=False),
                    ew.SingleSelectField(
                        name='collaborationtype',
                        options = [
                            ew.Option(
                                py_value='cooperation', 
                                selected=select_cooperation,
                                label='Cooperation'),
                            ew.Option(
                                py_value='participation',
                                selected=not select_cooperation,
                                label='Participation')],
                        validator=fev.UnicodeString(not_empty=True)),
                    ew.SingleSelectField(
                        name='status',
                        options = options,
                        validator=fev.UnicodeString(not_empty=True)),
                    ew.SubmitButton(
                        show_label=False,
                        attrs={'value':'Save'},
                        show_errors=False)])]
        return super(ChangeCollaborationStatusForm, self).display(**kw)
