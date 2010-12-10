from pylons import c

import ew as ew_core
import ew.jinja2_ew as ew

from allura.lib import validators as V
from allura import model as M

from .form_fields import AutoResizeTextarea
from .forms import ForgeForm

class OAuthApplicationForm(ForgeForm):
    submit_text='Register new applicaiton'
    class fields(ew_core.NameList):
        application_name =ew.TextField(label='Application Name',
                                       validator=V.UniqueOAuthApplicationName())
        application_description = AutoResizeTextarea(label='Application Description')

