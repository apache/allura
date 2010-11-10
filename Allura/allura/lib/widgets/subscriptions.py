from pylons import c

import ew as ew_core
import ew.jinja2_ew as ew

from allura.lib import validators as V
from allura import model as M

from .form_fields import SubmitButton

# Discussion forms
class _SubscriptionTable(ew.TableField):
    class hidden_fields(ew_core.NameList):
        _id = ew.HiddenField(validator=V.Ming(M.Mailbox))
        topic = ew.HiddenField()
        artifact_index_id = ew.HiddenField()
    class fields(ew_core.NameList):
        project_name = ew.HTMLField(label='Project', show_label=True)
        mount_point = ew.HTMLField(label='App', show_label=True)
        topic = ew.HTMLField(label='Topic', show_label=True)
        type = ew.HTMLField(label='Type', show_label=True)
        frequency = ew.HTMLField(label='Frequency', show_label=True)
        artifact_title = ew.HTMLField(label='Artifact', show_label=True)
        # unsubscribe = SubmitButton()
        unsubscribe = ew.Checkbox(suppress_label=True, show_label=True)

class SubscriptionForm(ew.SimpleForm):
    defaults=dict(
        ew.SimpleForm.defaults,
        submit_text='Unsubscribe from marked artifacts')
    class fields(ew_core.NameList):
        subscriptions=_SubscriptionTable()

class SubscribeForm(ew.SimpleForm):
    template='jinja:widgets/subscribe.html'
    defaults=dict(
        ew.SimpleForm.defaults,
        thing='tool',
        style='text',
        value=None)

    class fields(ew_core.NameList):
        subscribe=SubmitButton()
        unsubscribe=SubmitButton()

    def from_python(self, value, state):
        return value
