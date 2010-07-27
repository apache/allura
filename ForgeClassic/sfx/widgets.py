from pylons import c
from formencode import validators as fev

import ew

from pyforge.lib.widgets.forms import ForgeForm
from pyforge.lib import validators as V

from sfx import model as M

class _MailingListRow(ew.RowField):
    template='genshi:sfx.templates.list_admin_row'
    class hidden_fields(ew.WidgetsList):
        _id = ew.HiddenField(validator=V.Ming(M.List))
    class fields(ew.WidgetsList):
        name = ew.HTMLField(label='List Name', show_label=True)
        description = ew.TextField(label='Description', show_label=True)
        visibility = ew.SingleSelectField(label='Visibility', options=['public', 'private', 'hidden', 'delete'])

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
        public = ew.SingleSelectField(options=['yes', 'no'])
