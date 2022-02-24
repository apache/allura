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


class FollowToggle(ew.SimpleForm):
    template = 'jinja:forgeactivity:templates/widgets/follow.html'
    defaults = dict(
        ew.SimpleForm.defaults,
        thing='project',
        action='follow',
        action_label='follow',
        icon='star',
        following=False)

    class fields(ew_core.NameList):
        follow = ew.HiddenField(validator=fev.StringBool())

    def resources(self):
        yield ew.JSLink('activity_js/follow.js')

    def prepare_context(self, context):
        default_context = super().prepare_context({})
        if c.project.is_user_project:
            default_context.update(
                thing=c.project.user_project_of.display_name,
            )
        else:
            default_context.update(thing=c.project.name)
        default_context.update(context)
        return default_context

    def success_message(self, following):
        context = self.prepare_context({})
        return 'You are {state} {action}ing {thing}.'.format(
            state='now' if following else 'no longer',
            action=context['action_label'],
            thing=context['thing'],
        )
