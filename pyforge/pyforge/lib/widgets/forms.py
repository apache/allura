from pylons import c
from formencode import validators as fev

import ew

class ForgeForm(ew.SimpleForm):
    template='genshi:pyforge.lib.widgets.templates.forge_form'
    params=['submit_text']
    submit_text = 'Save'

    def display_field_by_idx(self, idx, ignore_errors=False):
        field = self.fields[idx]
        ctx = c.widget.context_for(field.name)
        display = field.display(**ctx)
        if ctx['errors'] and field.show_errors and not ignore_errors:
            display = "%s<div class='error'>%s</div>" % (display, ctx['errors'])
        return display

class NeighborhoodAddProjectForm(ForgeForm):
    submit_text = 'Create'

    @property
    def fields(self):
        fields = [
            ew.InputField(name='project_unixname', label='Project ID',
                          validator=fev.Regex(r'^[A-z][-A-z0-9]{2,}$', messages={'invalid':'Please use only letters, numbers, and dash characters.'})),
            ew.HiddenField(name='project_name', label='Project Name'),
            ew.HiddenField(name='project_description', label='Public Description')
        ]
        return fields