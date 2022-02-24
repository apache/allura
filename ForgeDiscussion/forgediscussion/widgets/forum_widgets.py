#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

from tg import tmpl_context as c
from formencode import validators as fev

import ew as ew_core
import ew.jinja2_ew as ew

from allura.lib import validators as V
from allura.lib.widgets import discuss as DW
from allura.lib.widgets import form_fields as ffw
from allura.lib.widgets.forms import CsrfForm
from allura.lib.widgets.subscriptions import SubscribeForm

from forgediscussion import model as M
import six


class _ThreadsTable(DW._ThreadsTable):

    class fields(ew_core.NameList):
        _id = ew.HiddenField(validator=V.Ming(M.ForumThread))
        subject = ffw.DisplayOnlyField(show_label=True, label='Subject')
        url = ffw.DisplayOnlyField()
        num_replies = ffw.DisplayOnlyField(
            show_label=True, label='Num Replies')
        num_views = ffw.DisplayOnlyField(show_label=True)
        flags = ffw.DisplayOnlyField(show_label=True)
        last_post = ffw.DisplayOnlyField(show_label=True)
        subscription = ew.Checkbox(suppress_label=True, show_label=True)
    defaults = dict(DW._ThreadsTable.defaults, div_id='forum_threads', allow_subscriptions=True)


class ThreadSubscriptionForm(DW.SubscriptionForm):

    class fields(ew_core.NameList):
        # Careful! using the same name as the prop on the model will invoke the RelationalProperty,
        # causing all related entities to be (re)fetched.
        _threads = _ThreadsTable()
        page_list = ffw.PageList()
        page_size = ffw.PageSize()


class AnnouncementsTable(DW._ThreadsTable):

    class fields(ew_core.NameList):
        _id = ew.HiddenField(validator=V.Ming(M.ForumThread))
        subject = ffw.DisplayOnlyField(show_label=True, label='Subject')
        url = ffw.DisplayOnlyField()
        num_replies = ffw.DisplayOnlyField(
            show_label=True, label='Num Replies')
        num_views = ffw.DisplayOnlyField(show_label=True)
        flags = ffw.DisplayOnlyField(show_label=True)
        last_post = ffw.DisplayOnlyField(show_label=True)
    defaults = dict(DW._ThreadsTable.defaults, div_id='announcements', allow_subscriptions=False)
    name = 'announcements'


class _ForumSelector(ew.SingleSelectField):

    def options(self):
        return [
            ew.Option(label=f.name, py_value=f, html_value=f.shortname)
            for f in c.app.forums]

    def to_python(self, value, state):
        result = M.Forum.query.get(
            shortname=value, app_config_id=c.app.config._id)
        if not result:
            raise fev.Invalid('Illegal forum shortname: %s' %
                              value, value, state)
        return result

    def from_python(self, value, state):
        if isinstance(value, str):
            return value
        else:
            return value.shortname


class ModerateThread(CsrfForm):
    submit_text = 'Save Changes'

    class fields(ew_core.NameList):
        subject = ew.InputField(label='Change subject:', attrs={'style':'width: 50%'})
        discussion = _ForumSelector(label='Move to different forum:')
        flags = ew.CheckboxSet(label='Options', options=['Sticky', 'Announcement'])

    class buttons(ew_core.NameList):
        delete = ew.SubmitButton(label='Delete Thread')


class ForumHeader(DW.HierWidget):
    template = 'jinja:forgediscussion:templates/discussion_widgets/forum_header.html'
    params = ['value']
    value = None
    widgets = dict(DW.HierWidget.widgets,
                   announcements_table=AnnouncementsTable(),
                   )


class ThreadHeader(DW.ThreadHeader):
    template = 'jinja:forgediscussion:templates/discussion_widgets/thread_header.html'
    defaults = dict(DW.ThreadHeader.defaults,
                    show_subject=True,
                    show_moderate=True)
    widgets = dict(DW.ThreadHeader.widgets,
                   moderate_thread=ModerateThread(),
                   announcements_table=AnnouncementsTable())


class Post(DW.Post):
    show_subject = False


class Thread(DW.Thread):
    defaults = dict(
        DW.Thread.defaults,
        show_subject=False)
    widgets = dict(DW.Thread.widgets,
                   thread_header=ThreadHeader(),
                   post=Post())


class Forum(DW.HierWidget):
    template = 'jinja:forgediscussion:templates/discussion_widgets/discussion.html'
    defaults = dict(
        DW.HierWidget.defaults,
        value=None,
        threads=None,
        show_subject=True,
        allow_create_thread=True
    )
    widgets = dict(DW.HierWidget.widgets,
                   subscription_form=ThreadSubscriptionForm()
                   )

    def resources(self):
        yield from super().resources()
