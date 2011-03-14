import ew
from ew import jinja2_ew
from allura.lib import validators as V

from forgetracker import model
from formencode import validators as fev

class BinForm(ew.SimpleForm):
    template='jinja:forgetracker:templates/tracker_widgets/bin_form.html'
    defaults=dict(
        ew.SimpleForm.defaults,
        submit_text = "Save Bin")

    class hidden_fields(ew.NameList):
        _id=jinja2_ew.HiddenField(validator=V.Ming(model.Bin), if_missing=None)

    class fields(ew.NameList):
        summary=jinja2_ew.TextField(
            label='Bin Name',
            validator=fev.UnicodeString(not_empty=True))
        terms=jinja2_ew.TextField(
            label='Search Terms',
            validator=fev.UnicodeString(not_empty=True))
