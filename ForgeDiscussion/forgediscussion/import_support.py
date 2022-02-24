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

import logging
from datetime import datetime

from ming import schema as S
from ming.orm import ThreadLocalORMSession, session

from tg import tmpl_context as c

from allura import model as M

from forgediscussion import model as DM
import six

log = logging.getLogger(__name__)


def validate_import(json, username_mapping, default_username=None):
    warnings = []
    schema = make_schema(username_mapping, default_username, warnings)
    json = schema.validate(json)
    return warnings, json


def perform_import(json, username_mapping, default_username=None, create_users=False):
    if create_users:
        default_username = create_user

    # Validate the import, create missing users
    warnings, json = validate_import(json, username_mapping, default_username)
    for w in warnings:
        log.warning('Importing to %s/%s: %s',
                    c.project.shortname,
                    c.app.config.options.mount_point,
                    w)

    for name, forum in json.forums.items():
        log.info('... %s has %d threads with %d total posts',
                 name, len(forum.threads), sum(len(t) for t in forum.threads.values()))

    for name, forum in json.forums.items():
        log.info('... creating %s/%s: %s',
                 c.project.shortname,
                 c.app.config.options.mount_point,
                 name)
        f = DM.Forum(
            app_config_id=c.app.config._id,
            name=forum['name'],
            shortname=forum['name'],
            description=forum['description'])
        for tid, posts in forum.threads.items():
            rest, head = posts[:-1], posts[-1]
            t = DM.ForumThread.new(
                _id=tid,
                discussion_id=f._id,
                subject=head['subject'])
            for p in posts:
                p = create_post(f._id, t._id, p)
            t.first_post_id = p._id
            ThreadLocalORMSession.flush_all()
            t.update_stats()
        ThreadLocalORMSession.flush_all()
        f.update_stats()
    return warnings


def make_schema(user_name_map, default_username, warnings):
    USER = AlluraUser(user_name_map, default_username, warnings)
    TIMESTAMP = TimeStamp()

    POST = {
        'msg_id': str,
        'is_followup_to': str,
        'is_deleted': str,
        'thread_id': str,
        'poster_name': str,
        'poster_user': USER,
        'subject': str,
        'date': TIMESTAMP,
        'body': str,
    }

    FORUM = {
        'name': str,
        'description': str,
        'threads': {str: [POST]},
    }

    result = S.SchemaItem.make({
        'class': str,
        'trackers': [None],
        'forums': {str: FORUM}
    })
    return result


class AlluraUser(S.FancySchemaItem):

    def __init__(self, mapping, default_username, warnings, **kw):
        self.mapping = mapping
        self.default_username = default_username
        self.warnings = warnings
        super().__init__(**kw)

    def _validate(self, value, **kw):
        value = S.String().validate(value)
        sf_username = self.mapping.get(value, value)
        result = M.User.by_username(sf_username)
        if result is None:
            self.warnings.append('User %s not found' % value)
            if callable(self.default_username):
                sf_username = self.default_username(value)
            else:
                sf_username = self.default_username
            self.warnings.append('... setting username to %r' % sf_username)
            result = M.User.by_username(sf_username)
            self.mapping[value] = sf_username
        return result

    def _from_python(self, value, state):
        return value.username


class TimeStamp(S.FancySchemaItem):

    def _validate(self, value, **kwargs):
        try:
            value = int(value)
        except TypeError:
            raise S.Invalid('%s is not int()-able' % value, value, None)
        value = datetime.utcfromtimestamp(value)
        return value


def create_user(json_username):
    allura_username = c.project.shortname + '-' + json_username
    while True:
        try:
            M.User.register(
                dict(
                    username=allura_username,
                    display_name=allura_username),
                False)
            session(M.User).flush()
            break
        except Exception:
            raise
    return allura_username


def create_post(discussion_id, thread_id, json_post):
    p = DM.ForumPost(
        _id='%s@import' % (json_post.msg_id),
        thread_id=thread_id,
        discussion_id=discussion_id,
        timestamp=json_post.date,
        author_id=json_post.poster_user._id,
        text=json_post.body,
        status='ok')
    if json_post.is_followup_to not in ('0', '-1'):
        p.parent_id = '%s@import' % (json_post['is_followup_to'])
    return p
