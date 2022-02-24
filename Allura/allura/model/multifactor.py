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
import typing

from ming import schema as S
from ming.odm import FieldProperty
from ming.odm.declarative import MappedClass

from .session import main_orm_session

if typing.TYPE_CHECKING:
    from ming.odm.mapper import Query

log = logging.getLogger(__name__)


class TotpKey(MappedClass):
    '''
    For use with "mongodb" TOTP service
    '''

    class __mongometa__:
        session = main_orm_session
        name = 'multifactor_totp'
        unique_indexes = ['user_id']

    query: 'Query[TotpKey]'

    _id = FieldProperty(S.ObjectId)
    user_id = FieldProperty(S.ObjectId, required=True)
    key = FieldProperty(S.Binary, required=True)  # S.Binary ok?  ming 0.5.x make_safe doesn't know about bytes/Binary


class RecoveryCode(MappedClass):
    '''
    For use with "mongodb" recovery code service
    '''

    class __mongometa__:
        session = main_orm_session
        name = 'multifactor_recovery_code'
        indexes = ['user_id']

    query: 'Query[RecoveryCode]'

    _id = FieldProperty(S.ObjectId)
    user_id = FieldProperty(S.ObjectId, required=True)
    code = FieldProperty(str, required=True)
