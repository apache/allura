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

import typing
import pymongo
from tg import config
from tg import tmpl_context as c
from ming.orm import FieldProperty, ForeignIdProperty, session
from datetime import datetime
from allura.model.auth import User
from allura import model as M

if typing.TYPE_CHECKING:
    from ming.odm.mapper import Query


class ShortUrl(M.Artifact):

    class __mongometa__:
        name = 'short_urls'
        unique_indexes = [('short_name', 'app_config_id')]

    query: 'Query[ShortUrl]'

    type_s = 'ShortUrl'
    full_url = FieldProperty(str)
    short_name = FieldProperty(str)
    description = FieldProperty(str)
    private = FieldProperty(bool)
    create_user = M.AlluraUserProperty()
    created = FieldProperty(datetime, if_missing=datetime.utcnow)
    last_updated = FieldProperty(datetime, if_missing=datetime.utcnow)

    @property
    def user(self):
        return User.query.get(_id=self.create_user)

    @classmethod
    def upsert(cls, shortname):
        u = cls.query.get(short_name=shortname, app_config_id=c.app.config._id)
        if u is not None:
            return u
        try:
            u = cls(short_name=shortname, app_config_id=c.app.config._id)
            session(u).flush(u)
        except pymongo.errors.DuplicateKeyError:
            session(u).expunge(u)
            u = cls.query.get(short_name=shortname,
                              app_config_id=c.app.config._id)
        return u

    def index(self):
        result = M.Artifact.index(self)
        result.update(
            full_url_s=self.full_url,
            short_name_s=self.short_name,
            description_s=self.description,
            title=f'{self.url()} => {self.full_url}',
            private_b=self.private,
            type_s=self.type_s)
        return result

    def url(self):
        return self.app.url + self.short_name

    @classmethod
    def build_short_url(cls, app, short_name):
        return config['short_url.url_pattern'].format(
            base_url=config['base_url'],
            nbhd=app.project.neighborhood.url_prefix.strip('/'),
            project=app.project.shortname,
            mount_point=app.config.options.mount_point,
            short_name=short_name)

    def short_url(self):
        return self.build_short_url(self.app, self.short_name)
