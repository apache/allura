from pylons import c
from formencode import validators as fev
from formencode import All
import formencode
from bson import ObjectId

import ew as ew_core
import ew.jinja2_ew as ew

from allura.lib.widgets import forms as ff
from allura.lib.widgets import form_fields as ffw
from allura.lib import helpers as h
from forgediscussion import model as DM

class OptionsAdmin(ff.AdminForm):
    defaults=dict(
        ff.ForgeForm.defaults,
        submit_text = 'Save')

    @property
    def fields(self):
        fields = [
            ew.SingleSelectField(
                name='PostingPolicy',
                label='Posting Policy',
                options=[
                    ew.Option(py_value='ApproveOnceModerated', label='Approve Once Moderated'),
                    ew.Option(py_value='ApproveAll', label='Approve All')]),
            ew.TextField(
                name='MonitoringEmail',
                label='Monitoring Email',
                validator=fev.Email())
        ]
        return fields

class AddForum(ff.AdminForm):
    template = 'jinja:forgediscussion:templates/discussion_widgets/add_forum.html'
    defaults=dict(
        ff.ForgeForm.defaults,
        name="add_forum",
        value=None,
        app=None,
        submit_text = 'Save')

    @property
    def fields(self):
        fields = [
            ew.HiddenField(name='app_id', label='App'),
            ew.TextField(name='name', label='Name', validator=fev.UnicodeString()),
            ew.TextField(name='shortname', label='Short Name',
                         validator=All(
                                 fev.Regex(ur"^[^\s\/\.]*$", not_empty=True, messages={
                                    'invalid':'Shortname cannot contain space . or /',
                                    'empty':'You must create a short name for the forum.'}),
                                 UniqueForumShortnameValidator())),
            ew.TextField(name='parent', label='Parent Forum'),
            ew.TextField(name='description', label='Description',validator=fev.UnicodeString()),
            ffw.FileChooser(name='icon', label='Icon'),
            ew.Checkbox(name="members_only", label="Members Only")
        ]
        return fields

class AddForumShort(AddForum):
    template = 'jinja:forgediscussion:templates/discussion_widgets/add_forum_short.html'

class UniqueForumShortnameValidator(fev.FancyValidator):

    def _to_python(self, value, state):
        forums = DM.Forum.query.find(dict(app_config_id=ObjectId(state.full_dict['app_id']))).all()
        value = h.really_unicode(value.lower() or '')
        if value in [ f.shortname for f in forums ]:
            raise formencode.Invalid('A forum already exists with that short name, please choose another.', value, state)
        return value
