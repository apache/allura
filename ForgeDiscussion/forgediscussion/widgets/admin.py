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

from formencode import validators as fev
from formencode import All
import formencode
from bson import ObjectId

import ew.jinja2_ew as ew

from allura.lib.widgets import forms as ff
from allura.lib import validators as v
from allura.lib import helpers as h
from forgediscussion import model as DM


class OptionsAdmin(ff.AdminForm):
    defaults = dict(
        ff.ForgeForm.defaults,
        submit_text='Save')

    @property
    def fields(self):
        fields = [
            ew.SingleSelectField(
                name='PostingPolicy',
                label='Posting Policy',
                options=[
                    ew.Option(py_value='ApproveOnceModerated',
                              label='Approve Once Moderated'),
                    ew.Option(py_value='ApproveAll', label='Approve All')]),
            ew.Checkbox(
                name='AllowEmailPosting',
                label='Allow posting replies via email')
        ]
        return fields


class AddForum(ff.AdminForm):
    template = 'jinja:forgediscussion:templates/discussion_widgets/add_forum.html'
    defaults = dict(
        ff.ForgeForm.defaults,
        name="add_forum",
        value=None,
        app=None,
        submit_text='Save')

    @property
    def fields(self):
        fields = [
            ew.HiddenField(name='app_id', label='App'),
            ew.TextField(name='name', label='Name',
                         validator=v.UnicodeString()),
            ew.TextField(name='shortname', label='Short Name',
                         validator=All(
                             fev.Regex(r"^[^\s\/\.]*$", not_empty=True, messages={
                                 'invalid': 'Shortname cannot contain space . or /',
                                 'empty': 'You must create a short name for the forum.'}),
                             UniqueForumShortnameValidator())),
            ew.TextField(name='parent', label='Parent Forum'),
            ew.TextField(name='description', label='Description',
                         validator=v.UnicodeString()),
            ew.TextField(name='monitoring_email',
                         label='Monitoring Email', validator=fev.Email()),
            ew.Checkbox(name="members_only", label="Developer Only"),
            ew.Checkbox(name="anon_posts", label="Allow Anonymous Posts")
        ]
        return fields


class AddForumShort(AddForum):
    template = 'jinja:forgediscussion:templates/discussion_widgets/add_forum_short.html'


class UniqueForumShortnameValidator(fev.FancyValidator):

    def _to_python(self, value, state):
        forums = DM.Forum.query.find(
            dict(app_config_id=ObjectId(state.full_dict['app_id']))).all()
        value = h.really_unicode(value.lower() or '')
        if value in [f.shortname for f in forums]:
            raise formencode.Invalid(
                'A forum already exists with that short name, please choose another.', value, state)
        return value
