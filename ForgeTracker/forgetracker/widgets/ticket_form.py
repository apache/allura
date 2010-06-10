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
        for field in model.Globals.for_current_tracker().custom_fields:
            if field.type == 'select':
                options = []
                for opt in field.options.split():
                    selected = False
                    if opt.startswith('*'):
                        opt = opt[1:]
                        selected = True
                    options.append(ew.Option(label=opt,html_value=opt,py_value=opt,selected=selected))
                fields.append(ew.SingleSelectField(label=field.label, name=str(field.name),
                    options=options))
            elif field.type == 'boolean':
                fields.append(ew.Checkbox(label=field.label, name=str(field.name), suppress_label=True))
            elif field.type == 'sum' or field.type == 'number':
                fields.append(ew.NumberField(label=field.label, name=str(field.name)))
            else:
                fields.append(ew.TextField(label=field.label, name=str(field.name)))
        return fields

class EditTicketCustomFields(TicketCustomFields):
    template='genshi:forgetracker.widgets.templates.edit_ticket_custom_fields'

class GenericTicketForm(ew.SimpleForm):
    name="ticket_form"
    submit_text='Save Ticket'
    ticket=None
    params=['submit_text','ticket']

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
            ew.TextField(name='summary', label='Name', validator=fev.UnicodeString(not_empty=True)),
            ffw.MarkdownEdit(label='Description',name='description'),
            ew.SingleSelectField(name='status', label='Status',
                options=lambda: model.Globals.for_current_tracker().status_names.split()),
            ffw.ProjectUserSelect(name='assigned_to', label='Assigned To'),
            ew.SingleSelectField(name='milestone', label='Milestone',
                options=lambda: [ew.Option(label='None',html_value='',py_value='')] +
                                model.Globals.for_current_tracker().milestone_names.split()),
            ffw.LabelEdit(label='Tags',name='labels', className='ticket_form_tags'),
            ew.SubmitButton(label=self.submit_text,name='submit',
                attrs={'class':"ui-button ui-widget ui-state-default ui-button-text-only"}),
            ew.HiddenField(name='ticket_num', validator=fev.Int(if_missing=None)),
            ew.HiddenField(name='super_id', validator=fev.UnicodeString(if_missing=None)) ]
        return fields

class TicketForm(GenericTicketForm):
    template='genshi:forgetracker.widgets.templates.ticket_form'
    @property
    def fields(self):
        fields = super(TicketForm, self).fields
        if model.Globals.for_current_tracker().custom_fields:
            fields.append(TicketCustomFields(name="custom_fields"))
        return fields

class EditTicketForm(GenericTicketForm):
    template='genshi:forgetracker.widgets.templates.edit_ticket_form'
    name="edit_ticket_form"
    @property
    def fields(self):
        fields = super(EditTicketForm, self).fields
        if model.Globals.for_current_tracker().custom_fields:
            fields.append(EditTicketCustomFields(name="custom_fields"))
        return fields
    def resources(self):
        for r in super(EditTicketForm, self).resources(): yield r
        yield ew.CSSScript('''
            #sidebar-right select{ margin: 0;}
            #sidebar-right input.title{ padding: 0; margin: 0;}
            #sidebar-right input[type="checkbox"], input[type="radio"], input.checkbox, input.radio{
                top: 0;
            }
        ''')
