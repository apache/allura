from pylons import c

import ew

from pyforge.lib import validators as V
from pyforge.lib import helpers as h
from pyforge import model as M

from .form_fields import SubmitButton

# Discussion forms
class _SubscriptionTable(ew.TableField):
    class hidden_fields(ew.WidgetsList):
        _id = ew.HiddenField(validator=V.Ming(M.Subscriptions))
        topic = ew.HiddenField()
        artifact_index_id = ew.HiddenField()
    class fields(ew.WidgetsList):
        project_name = ew.HTMLField(label='Project', show_label=True)
        mount_point = ew.HTMLField(label='App', show_label=True)
        topic = ew.HTMLField(label='Topic', show_label=True)
        type = ew.HTMLField(label='Type', show_label=True)
        frequency = ew.HTMLField(label='Frequency', show_label=True)
        artifact = ew.HTMLField(label='Artifact', show_label=True)
        unsubscribe = SubmitButton()

class SubscriptionForm(ew.SimpleForm):
    class fields(ew.WidgetsList):
        subscriptions=_SubscriptionTable()
    submit_text=None

class SubscribeForm(ew.SimpleForm):
    template='pyforge.lib.widgets.templates.subscribe'
    params=['thing']
    thing='plugin'
    class fields(ew.WidgetsList):
        subscribe=SubmitButton()
        unsubscribe=SubmitButton()
