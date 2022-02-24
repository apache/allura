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

from ming.orm import FieldProperty
from ming import schema as S
from datetime import datetime, timedelta
import typing
from ming.orm import Mapper
from tg import request

from allura.lib import plugin
from allura.model.session import main_orm_session
from allura.model import Stats

if typing.TYPE_CHECKING:
    from ming.odm.mapper import Query


class UserStats(Stats):

    class __mongometa__:
        name = 'userstats'
        session = main_orm_session
        unique_indexes = ['_id', 'user_id']

    query: 'Query[UserStats]'

    tot_logins_count = FieldProperty(int, if_missing=0)
    last_login = FieldProperty(datetime)
    lastmonthlogins = FieldProperty([datetime])
    user_id = FieldProperty(S.ObjectId)

    @classmethod
    def create(cls, user):
        auth_provider = plugin.AuthenticationProvider.get(request)
        reg_date = auth_provider.user_registration_date(user)
        stats = cls.query.get(user_id=user._id)
        if stats:
            return stats
        stats = cls(user_id=user._id, registration_date=reg_date)
        user.stats_id = stats._id
        return stats

    def getLastMonthLogins(self):
        self.checkOldArtifacts()
        return len(self.lastmonthlogins)

    def checkOldArtifacts(self):
        super().checkOldArtifacts()
        now = datetime.utcnow()
        for l in self.lastmonthlogins:
            if now - l > timedelta(30):
                self.lastmonthlogins.remove(l)

    def addLogin(self, login_datetime):
        if (not self.last_login) or (login_datetime > self.last_login):
            self.last_login = login_datetime
        self.tot_logins_count += 1
        self.lastmonthlogins.append(login_datetime)
        self.checkOldArtifacts()

Mapper.compile_all()
