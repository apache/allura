from formencode import validators as fev

import ew as ew_core
import ew.jinja2_ew as ew

from allura.lib.widgets.forms import ForgeForm

class ImportForm(ForgeForm):
    submit_text='Import'
    class fields(ew_core.NameList):
        checkout_url = ew.TextField(label='Checkout URL',
                                    validator=fev.URL())
