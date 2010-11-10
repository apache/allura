import ew as ew_core
import ew.jinja2_ew as ew

from allura.lib.widgets import form_fields as ffw
from allura.lib.widgets import forms
from allura import model as M

class NewPostForm(forms.ForgeForm):
    class fields(ew_core.NameList):
        title = ew.TextField()
        text = ffw.MarkdownEdit(show_label=False)
        date = ew.DateField()
        time = ew.TimeField()
        state = ew.SingleSelectField(
            options=[
                ew.Option(py_value='draft', label='Draft'),
                ew.Option(py_value='published', label='Published') ])
        labels = ffw.LabelEdit()

class EditPostForm(NewPostForm):
    class buttons(ew_core.NameList):
        delete = ew.SubmitButton()

class ViewPostForm(ew_core.Widget):
    template='jinja:blog_widgets/view_post.html'
    defaults=dict(
        ew_core.Widget.defaults,
        value=None,
        subscribed=None,
        base_post=None)

    def __call__(self, **kw):
        kw = super(ViewPostForm, self).__call__(**kw)
        kw['subscribed'] = \
            M.Mailbox.subscribed(artifact=kw.get('value'))
        return kw

class PreviewPostForm(ew_core.Widget):
    template='jinja:blog_widgets/preview_post.html'
    defaults=dict(
        ew_core.Widget.defaults,
        value=None)
