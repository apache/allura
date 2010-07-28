from pylons import c
from formencode import validators as fev

import ew

from pyforge.lib.widgets.forms import ForgeForm
from pyforge.lib import validators as V

from sfx import model as M

class _MailingListRow(ew.RowField):
    template='genshi:sfx.templates.list_admin_row'
    class hidden_fields(ew.WidgetsList):
        name = ew.HiddenField()
    class fields(ew.WidgetsList):
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

    class fields(ew.WidgetsList):
        lists = ew.TableField(field=_MailingListRow())

class NewList(ForgeForm):
    template='genshi:sfx.templates.new_list'
    submit_text = 'Create'
    enctype=None

    class fields(ew.WidgetsList):
        name = ew.TextField()
        description = ew.TextField()
        is_public = ew.SingleSelectField(
            validator=fev.Int(),
            options=[ew.Option(label='Yes', py_value=M.List.PUBLIC),
                     ew.Option(label='No', py_value=M.List.PRIVATE)])
