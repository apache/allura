import tw.forms as twf
import ew
from pyforge.lib.widgets import form_fields as ffw

from pylons import c
from forgetracker import model
from formencode import validators as fev

class TicketCustomFields(ew.CompoundField):
    template='genshi:forgetracker.widgets.templates.ticket_custom_fields'
    @property
    def fields(self):
        fields = []
        for field in model.Globals.query.get(app_config_id=c.app.config._id).custom_fields:
            if field.type == 'select':
                fields.append(ew.SingleSelectField(label=field.label, name=str(field.name), attrs={'class':"title wide"},
                    options=[ew.Option(label=opt,html_value=opt,py_value=opt) for opt in field.options.split()]))
            elif field.type == 'boolean':
                fields.append(ew.Checkbox(label=field.label, name=str(field.name), suppress_label=True))
            elif field.type == 'sum' or field.type == 'number':
                fields.append(ew.NumberField(label=field.label, name=str(field.name), attrs={'class':"title wide"}))
            else:
                fields.append(ew.TextField(label=field.label, name=str(field.name), attrs={'class':"title wide"}))
        return fields

class TicketForm(ew.SimpleForm):
    template='genshi:forgetracker.widgets.templates.ticket_form'
    name="ticket_form"
    submit_text='Save Ticket'
    params=['submit_text']

    def display_field_by_idx(self, idx, ignore_errors=False):
        field = self.fields[idx]
        ctx = c.widget.context_for(field.name)
        display = field.display(**ctx)
        if ctx['errors'] and field.show_errors and not ignore_errors:
            display = "%s<div class='error'>%s</div>" % (display, ctx['errors'])
        return display

    @property
    def fields(self):
        fields = [
            ew.TextField(name='summary', label='Name', attrs={'class':"title wide"}, validator=fev.UnicodeString(not_empty=True)),
            ffw.MarkdownEdit(label='Description',name='description'),
            ew.SingleSelectField(name='status', label='Status', attrs={'class':"title wide"},
                options=lambda: model.Globals.query.get(app_config_id=c.app.config._id).status_names.split()),
            ffw.ProjectUserSelect(name='assigned_to', label='Assigned To'),
            ew.SingleSelectField(name='milestone', label='Milestone', attrs={'class':"title wide"},
                options=lambda: [ew.Option(label='None',html_value='',py_value='')] +
                                model.Globals.query.get(app_config_id=c.app.config._id).milestone_names.split()),
            ffw.LabelEdit(label='Tags',name='labels', className='title wide ticket_form_tags'),
            ew.SubmitButton(label=self.submit_text,name='submit',
                attrs={'class':"ui-button ui-widget ui-state-default ui-button-text-only"}),
            ew.HiddenField(name='ticket_num', validator=fev.UnicodeString(if_missing=None)),
            ew.HiddenField(name='super_id', validator=fev.UnicodeString(if_missing=None)) ]
        if model.Globals.query.get(app_config_id=c.app.config._id).custom_fields:
            fields.append(TicketCustomFields(name="custom_fields"))
        return fields
