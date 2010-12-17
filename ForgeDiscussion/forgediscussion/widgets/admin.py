from pylons import c
from formencode import validators as fev

import ew as ew_core
import ew.jinja2_ew as ew

from allura.lib.widgets import forms as ff

class OptionsAdmin(ff.AdminForm):
    defaults=dict(
        ff.ForgeForm.defaults,
        submit_text = 'Save')

    @property
    def fields(self):
        fields = [
            ew.SingleSelectField(
                name='PostingPolicy',
                label='Posting Policy',
                options=[
                    ew.Option(py_value='ApproveOnceModerated', label='Approve Once Moderated'),
                    ew.Option(py_value='ApproveAll', label='Approve All')])
        ]
        return fields
