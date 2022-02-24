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

from datetime import datetime
import typing

from ming import schema as S
from ming.orm import FieldProperty, Mapper
from ming.orm.declarative import MappedClass

from allura import model as M
from allura.model.types import MarkdownCache

if typing.TYPE_CHECKING:
    from ming.odm.mapper import Query


class ChatChannel(MappedClass):

    class __mongometa__:
        name = 'globals'
        session = M.main_orm_session
        indexes = ['project_id']
        unique_indexes = ['channel']

    query: 'Query[ChatChannel]'

    _id = FieldProperty(S.ObjectId)
    project_id = FieldProperty(S.ObjectId)
    app_config_id = FieldProperty(S.ObjectId)
    channel = FieldProperty(str)


class ChatMessage(M.Artifact):

    class __mongometa__:
        name = 'chat_message'
        indexes = ['timestamp']

    query: 'Query[ChatMessage]'

    type_s = 'Chat Message'

    timestamp = FieldProperty(datetime, if_missing=datetime.utcnow)
    sender = FieldProperty(str, if_missing='')
    channel = FieldProperty(str, if_missing='')
    text = FieldProperty(str, if_missing='')
    text_cache = FieldProperty(MarkdownCache)

    def index_id(self):
        id = 'Chat-{}:{}:{}.{}'.format(
            self.channel,
            self.sender,
            self.timestamp.isoformat(),
            self._id)
        return id.replace('.', '/')

    def index(self):
        result = super().index()
        result.update(
            snippet_s=f'{self.sender} > {self.text}',
            sender_t=self.sender,
            text=self.text)
        return result

    def url(self):
        return (self.app_config.url()
                + self.timestamp.strftime('%Y/%m/%d/#')
                + str(self._id))

    def shorthand_id(self):
        return str(self._id)  # pragma no cover

    @property
    def sender_short(self):
        return self.sender.split('!')[0]

    @property
    def timestamp_hour(self):
        return self.timestamp.strftime('%H:%M:%S')

Mapper.compile_all()
