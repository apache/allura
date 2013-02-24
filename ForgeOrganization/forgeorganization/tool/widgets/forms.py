from allura.lib import validators as V
from allura.lib.widgets.forms import ForgeForm

from formencode import validators as fev

import ew as ew_core
import ew.jinja2_ew as ew

class SearchOrganizationForm(ForgeForm):
    defaults=dict(ForgeForm.defaults, submit_text='Search')

    class fields(ew_core.NameList):
        organization=ew.TextField(
            label='Organization',
            validator=fev.UnicodeString(not_empty=True))

class InviteOrganizationForm(ForgeForm):
    defaults=dict(ForgeForm.defaults, submit_text=None, show_errors=False)

    def display(self, **kw):
        org = kw.get('organization')
        orgnamefield = '<a href="%s">%s</a>' % (org.url(), org.fullname)

        self.fields = [
            ew.RowField(
                show_errors=False,
                hidden_fields=[
                    ew.HiddenField(
                        name="organizationid",
                        attrs={'value':str(org._id)},
                        show_errors=False)
                ],
                fields=[
                    ew.HTMLField(
                        text=orgnamefield,
                        show_errors=False),
                    ew.SingleSelectField(
                        name='collaborationtype',
                        options = [
                            ew.Option(
                                py_value='cooperation', 
                                label='Cooperation'),
                            ew.Option(
                                py_value='participation',
                                label='Participation')],
                        validator=fev.UnicodeString(not_empty=True)),
                    ew.SubmitButton(
                        show_label=False,
                        attrs={'value':'Invite'},
                        show_errors=False)])]
        return super(InviteOrganizationForm, self).display(**kw)

class SendCollaborationRequestForm(ForgeForm):
    defaults=dict(ForgeForm.defaults, submit_text='Send')

    class fields(ew_core.NameList):
        organization = ew.SingleSelectField(
            label='Organization',
            options = [],
            validator=fev.UnicodeString(not_empty=True))

        coll_type = ew.SingleSelectField(
            label='Collaboration Type',
            options = [
                ew.Option(
                    py_value='cooperation', 
                    label='Cooperation'),
                ew.Option(
                    py_value='participation',
                    label='Participation')],
             validator=fev.UnicodeString(not_empty=True))

    def display(self, **kw):
        orgs = kw.get('organizations')
        opts=[ew.Option(py_value=org._id,label=org.fullname) for org in orgs]
        self.fields['organization'].options = opts
        return super(SendCollaborationRequestForm, self).display(**kw)

class ChangeCollaborationStatusForm(ForgeForm):
    defaults=dict(ForgeForm.defaults, submit_text=None, show_errors=False)

    def display(self, **kw):
        coll = kw.get('collaboration')
        org = coll.organization
        orgnamefield = '<a href="%s">%s</a>' % (org.url(), org.fullname)
        
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
                    label='Decline request',
                    selected=False),
                ew.Option(
                    py_value='active',
                    label='Accept request',
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
                        text=orgnamefield,
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

