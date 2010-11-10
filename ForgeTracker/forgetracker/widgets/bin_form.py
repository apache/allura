import tw.forms as twf
import ew
from allura.lib.widgets import form_fields as ffw

from pylons import c
from forgetracker import model
from formencode import validators as fev

class BinForm(ew.SimpleForm):
    template='jinja:tracker_widgets/bin_form.html'
    defaults=dict(
        ew.SimpleForm.defaults,
        name="bin_form",
        submit_text = "Save Bin")

    @property
    def fields(self):
        fields = [
            ew.TextField(name='summary', label='Bin Name', validator=fev.UnicodeString(not_empty=True)),
            ew.TextField(name='terms', label='Search Terms', validator=fev.UnicodeString(not_empty=True)),
            ew.HiddenField(name='old_summary', label='Old Name', validator=fev.UnicodeString()),
            ew.HiddenField(name='sort', label='Sort Order', validator=fev.UnicodeString())]
        return fields
