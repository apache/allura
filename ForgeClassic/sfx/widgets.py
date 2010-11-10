from pylons import c
from formencode import validators as fev
from formencode import schema as fes

import ew as ew_core
import ew.jinja2_ew as ew

from allura.lib.widgets.forms import ForgeForm
from allura.lib import validators as V

from sfx import model as M

class _MailingListRow(ew.RowField):
    template='jinja:sfx/list_admin_row.html'
    class hidden_fields(ew_core.NameList):
        name = ew.HiddenField()
    class fields(ew_core.NameList):
        name = ew.HTMLField(label='List Name', show_label=True)
        description = ew.TextField(label='Description', show_label=True)
        is_public = ew.SingleSelectField(
            label='Visibility',
            validator=fev.Int(),
            options=[ew.Option(label='Public', py_value=M.List.PUBLIC),
                     ew.Option(label='Private', py_value=M.List.PRIVATE),
                     ew.Option(label='Hidden', py_value=M.List.HIDDEN),
                     ew.Option(label='Delete', py_value=M.List.DELETE)])

class ListAdmin(ew.SimpleForm):
    submit_text = 'Save'
    enctype=None

    class fields(ew_core.NameList):
        lists = ew.TableField(field=_MailingListRow())

class NewList(ForgeForm):
    template='jinja:sfx/new_list.html'
    submit_text = 'Create'
    enctype=None

    class fields(ew_core.NameList):
        name = ew.TextField()
        description = ew.TextField()
        is_public = ew.SingleSelectField(
            validator=fev.Int(),
            options=[ew.Option(label='Yes', py_value=M.List.PUBLIC),
                     ew.Option(label='No', py_value=M.List.PRIVATE)])

class SubscriberSearch(ForgeForm):
    submit_text = 'Search'

    class fields(ew_core.NameList):
        search_criteria = ew.TextField()
        sort_by = ew.SingleSelectField(
            options=[ ew.Option(label='User name', py_value='user name'),
                      ew.Option(label='Host name/Domain name',
                                py_value='host name/domain name'),
                      ])

class PasswordChange(ForgeForm):
    submit_text = 'Save'

    class fields(ew_core.NameList):
        new_password=ew.TextField(field_type='password')
        confirm_password=ew.TextField(field_type='password')

    def validate(self, value, state):
        msg = None
        pwd = value['new_password']
        if pwd != value['confirm_password']:
            msg = 'The same password must be entered twice verbatim'
        elif len(pwd) < 4 or len(pwd) > 16:
            msg = 'The password must 4-16 chars.'
        elif not pwd.isalnum():
            msg = 'The password must contain letters and numbers only.'
        if msg is None:
            return value
        exc = fev.Invalid(msg, value, state, error_dict=dict(
            new_password=fev.Invalid(msg, value, state),
            confirm_password=fev.Invalid(msg, value, state)))
        raise exc

class NewVHost(ForgeForm):
    submit_text = 'Create'
    enctype=None

    class fields(ew_core.NameList):
        name=ew.TextField(label='New virtual host', attrs=dict(title='(e.g. vhost.org)'))

class MySQLPassword(ForgeForm):
    defaults=dict(
        ForgeForm.defaults,
        submit_text='Set passwords')

    @property
    def fields(self):
        gid = c.project.get_tool_data('sfx', 'group_id')
        name = c.project.get_tool_data('sfx', 'unix_group_name')
        prefix=str(name)[0] + str(gid)
        return [
            ew.TextField(label=prefix+'ro', name='passwd_rouser'),
            ew.TextField(label=prefix+'rw', name='passwd_rwuser'),
            ew.TextField(label=prefix+'admin', name='passwd_adminuser')]
