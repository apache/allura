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

from ming.odm import FieldProperty
from allura.model import Artifact


class Webhook(Artifact):

    class __mongometa__:
        name = 'webhook'
        unique_indexes = [('app_config_id', 'type', 'hook_url')]

    type = FieldProperty(str)
    hook_url = FieldProperty(str)
    secret = FieldProperty(str)

    def url(self):
        return '{}{}/{}/{}'.format(
            self.app_config.project.url(),
            'admin/webhooks',
            self.type,
            self._id)

    @classmethod
    def find(cls, type, project):
        ac_ids = [ac._id for ac in project.app_configs]
        hooks = cls.query.find(dict(type=type, app_config_id={'$in': ac_ids}))
        return hooks.all()
