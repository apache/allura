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
import six.moves.urllib.request
import six.moves.urllib.parse
import six.moves.urllib.error
import typing
from datetime import datetime

from bson import ObjectId
from tg import tmpl_context as c
from ming import schema
from ming.orm import Mapper
from ming.orm import FieldProperty, ForeignIdProperty, RelationProperty

# Pyforge-specific imports

from allura.model.artifact import VersionedArtifact
from allura.model.auth import AlluraUserProperty, User
from allura.model.project import ProjectRole
from allura.model.timeline import ActivityObject
from allura.lib import helpers as h

if typing.TYPE_CHECKING:
    from ming.odm.mapper import Query

log = logging.getLogger(__name__)


class Feedback(VersionedArtifact, ActivityObject):

    class __mongometa__:
        name = 'feedback'
        indexes = [
            ('project_id', 'reported_by_id'),
        ]

    query: 'Query[Feedback]'

    type_s = 'Feedback'

    _id = FieldProperty(schema.ObjectId)
    created_date = FieldProperty(datetime, if_missing=datetime.utcnow)
    rating = FieldProperty(str, if_missing='')
    description = FieldProperty(str, if_missing='')
    reported_by_id: ObjectId = AlluraUserProperty(if_missing=lambda: c.user._id)
    project_id = ForeignIdProperty('Project', if_missing=lambda: c.project._id)
    reported_by = RelationProperty(User, via='reported_by_id')

    def index(self):
        result = VersionedArtifact.index(self)
        result.update(
            created_date_dt=self.created_date,
            reported_by_username_t=self.reported_by.username,
            text=self.description,
        )
        return result

    @property
    def activity_name(self):
        return 'a review comment'

    @property
    def activity_extras(self):
        d = ActivityObject.activity_extras.fget(self)
        d.update(summary=self.description)
        return d

    def url(self):
        return self.app_config.url()


Mapper.compile_all()
