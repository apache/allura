import tw.forms as twf
import ew
from pyforge.lib.widgets import form_fields as ffw

from pylons import c
from forgetracker import model
from formencode import validators as fev

class BinForm(ew.SimpleForm):
    name="bin_form"
    submit_text = "Save Bin"

    @property
    def fields(self):
        fields = [
            ew.TextField(name='summary', label='Bin Name', validator=fev.UnicodeString(not_empty=True)),
            ew.TextField(name='terms', label='Search Terms', validator=fev.UnicodeString(not_empty=True))]
        return fields