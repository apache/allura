from pylons import tmpl_context as c

import ew as ew_core
import ew.jinja2_ew as ew

from allura.lib import validators as V
from allura.lib.widgets import form_fields as ffw
from allura import model as M

from .form_fields import SubmitButton

# Discussion forms
class _SubscriptionTable(ew.TableField):
    class hidden_fields(ew_core.NameList):
        subscription_id = ew.HiddenField(validator=V.Ming(M.Mailbox))
        tool_id = ew.HiddenField()
        project_id = ew.HiddenField()
        topic = ew.HiddenField()
        artifact_index_id = ew.HiddenField()
    class fields(ew_core.NameList):
        project_name = ffw.DisplayOnlyField(label='Project', show_label=True, with_hidden_input=False)
        mount_point = ffw.DisplayOnlyField(label='App', show_label=True, with_hidden_input=False)
        topic = ffw.DisplayOnlyField(label='Topic', show_label=True, with_hidden_input=False)
        type = ffw.DisplayOnlyField(label='Type', show_label=True, with_hidden_input=False)
        frequency = ffw.DisplayOnlyField(label='Frequency', show_label=True, with_hidden_input=False)
        artifact_title = ew.LinkField(label='Artifact', show_label=True, plaintext_if_no_href=True)
        # unsubscribe = SubmitButton()
        subscribed = ew.Checkbox(suppress_label=True)

class SubscriptionForm(ew.SimpleForm):
    defaults=dict(
        ew.SimpleForm.defaults,
        submit_text='Save')
    class fields(ew_core.NameList):
        subscriptions=_SubscriptionTable()

class SubscribeForm(ew.SimpleForm):
    template='jinja:allura:templates/widgets/subscribe.html'
    defaults=dict(
        ew.SimpleForm.defaults,
        thing='tool',
        style='text',
        tool_subscribed=False,
        value=None)

    class fields(ew_core.NameList):
        subscribe=SubmitButton()
        unsubscribe=SubmitButton()
        shortname=ew.HiddenField()

    def from_python(self, value, state):
        return value
