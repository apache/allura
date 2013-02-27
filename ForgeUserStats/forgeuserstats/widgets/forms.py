from allura.lib import validators as V
from allura.lib.widgets.forms import ForgeForm

from formencode import validators as fev

import ew as ew_core
import ew.jinja2_ew as ew

class StatsPreferencesForm(ForgeForm):
    defaults=dict(ForgeForm.defaults)

    class fields(ew_core.NameList):
        visible = ew.Checkbox(
            label='Make my personal statistics visible to other users.')
            
    def display(self, **kw):
        if kw.get('user').stats.visible:
            self.fields['visible'].attrs = {'checked':'true'}      
        else:
            self.fields['visible'].attrs = {}    
        return super(ForgeForm, self).display(**kw)

