import tw.forms as twf
import ew
from pyforge.lib.widgets import form_fields as ffw

from pylons import c
from forgetracker import model

class TicketCustomFields(ew.CompoundField):
    template='genshi:forgetracker.widgets.templates.ticket_custom_fields'
    @property
    def fields(self):
        fields = []
        for field in model.Globals.query.get(app_config_id=c.app.config._id).custom_fields:
            if field.type != 'select' and field.type != 'boolean':
                fields.append(ew.InputField(label=field.label, name=field.name, attrs={'class':"title wide"}))
            elif field.type == 'boolean':
                fields.append(ew.Checkbox(label=field.label, name=field.name, suppress_label=True, value=True))
            else:
                fields.append(ew.SingleSelectField(label=field.label, name=field.name, attrs={'class':"title wide"},
                    options=[ew.Option(label=opt,html_value=opt,py_value=opt) for opt in field.options.split()]))
        return fields

class TicketForm(ew.SimpleForm):
    template='genshi:forgetracker.widgets.templates.ticket_form'
    submit_text='Save Ticket'
    user_tags = []
    params=['user_tags', 'submit_text']

    def display_field_by_idx(self, idx):
        return self.fields[idx].display(**c.widget.context_for(self.fields[idx].name))

    @property
    def fields(self):
        fields = [
            ew.InputField(name='summary', label='Name', attrs={'class':"title wide"}),
            ffw.MarkdownEdit(label='Description',name='description'),
            ew.SingleSelectField(name='status', label='Status', attrs={'class':"title wide"},
                options=lambda: model.Globals.query.get(app_config_id=c.app.config._id).status_names.split()),
            ffw.ProjectUserSelect(name='assigned_to', label='Assigned To'),
            ew.SingleSelectField(name='milestone', label='Milestone', attrs={'class':"title wide"},
                options=lambda: [ew.Option(label='None',html_value='',py_value='')] +
                                model.Globals.query.get(app_config_id=c.app.config._id).milestone_names.split()),
            ffw.UserTagEdit(label='Tags',name='tags', className='title wide'),
            ew.SubmitButton(label=self.submit_text,name='submit',
                attrs={'class':"ui-button ui-widget ui-state-default ui-button-text-only"}),
            ew.HiddenField(name='ticket_num'),
            ew.HiddenField(name='super_id'),
            TicketCustomFields(name="custom_fields")
        ]
        return fields