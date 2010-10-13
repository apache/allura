from pylons import c

import ew

from allura.lib import validators as V
from allura.lib import helpers as h
from allura import model as M

from .form_fields import SubmitButton

# Discussion forms
class _SubscriptionTable(ew.TableField):
    class hidden_fields(ew.WidgetsList):
        _id = ew.HiddenField(validator=V.Ming(M.Mailbox))
        topic = ew.HiddenField()
        artifact_index_id = ew.HiddenField()
    class fields(ew.WidgetsList):
        project_name = ew.HTMLField(label='Project', show_label=True)
        mount_point = ew.HTMLField(label='App', show_label=True)
        topic = ew.HTMLField(label='Topic', show_label=True)
        type = ew.HTMLField(label='Type', show_label=True)
        frequency = ew.HTMLField(label='Frequency', show_label=True)
        artifact_title = ew.HTMLField(label='Artifact', show_label=True)
        # unsubscribe = SubmitButton()
        unsubscribe = ew.Checkbox(suppress_label=True, show_label=True)

class SubscriptionForm(ew.SimpleForm):
    class fields(ew.WidgetsList):
        subscriptions=_SubscriptionTable()
    submit_text='Unsubscribe from marked artifacts'

class SubscribeForm(ew.SimpleForm):
    template='jinja:widgets/subscribe.html'
    params=['thing','style', 'value']
    thing='tool'
    style='text'
    value=None
    perform_validation=False
    class fields(ew.WidgetsList):
        subscribe=SubmitButton()
        unsubscribe=SubmitButton()
