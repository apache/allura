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

import datetime as dt
import json
import typing

from ming.odm import FieldProperty, session
from paste.deploy.converters import asint
from tg import config

from allura.model import Artifact
from allura.lib import helpers as h
import six

if typing.TYPE_CHECKING:
    from ming.odm.mapper import Query


class Webhook(Artifact):
    class __mongometa__:
        name = 'webhook'
        unique_indexes = [('app_config_id', 'type', 'hook_url')]

    query: 'Query[Webhook]'

    type = FieldProperty(str)
    hook_url = FieldProperty(str)
    secret = FieldProperty(str)
    last_sent = FieldProperty(dt.datetime, if_missing=None)

    def url(self):
        app = self.app_config.load()
        app = app(self.app_config.project, self.app_config)
        return f'{app.admin_url}webhooks/{self.type}/{self._id}'

    def enforce_limit(self):
        '''Returns False if limit is reached, otherwise True'''
        if self.last_sent is None:
            return True
        now = dt.datetime.utcnow()
        config_type = self.type.replace('-', '_')
        limit = asint(config.get('webhook.%s.limit' % config_type, 30))
        if (now - self.last_sent) > dt.timedelta(seconds=limit):
            return True
        return False

    def update_limit(self):
        self.last_sent = dt.datetime.utcnow()
        session(self).flush(self)

    @classmethod
    def max_hooks(self, type, tool_name):
        type = type.replace('-', '_')
        limits = json.loads(config.get('webhook.%s.max_hooks' % type, '{}'))
        return limits.get(tool_name.lower(), 3)

    def __json__(self):
        return {
            '_id': str(self._id),
            'url': h.absurl('/rest' + self.url()),
            'type': str(self.type),
            'hook_url': str(self.hook_url),
            'mod_date': self.mod_date,
        }
