import ew as ew_core
import ew.jinja2_ew as ew

from formencode import validators as fev

from allura.lib.widgets import form_fields as ffw
from allura.lib.widgets import forms
from allura import model as M

class ViewMetricsForm(ew_core.Widget):
    template='jinja:forgeblog:templates/metrics_widgets/view_metrics.html'
    defaults=dict(
        ew_core.Widget.defaults,
        value=None,
        subscribed=None,
        base_post=None)

    def __call__(self, **kw):
        kw = super(ViewMetricsForm, self).__call__(**kw)
        kw['subscribed'] = \
            M.Mailbox.subscribed(artifact=kw.get('value'))
        return kw