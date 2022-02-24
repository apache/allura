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

from ming.base import Object
from ming import schema as S

EVERYONE, ALL_PERMISSIONS = None, '*'


class MarkdownCache(S.Object):

    def __init__(self, **kw):
        super().__init__(
            fields=dict(
                md5=S.String(),
                fix7528=S.Anything,
                html=S.String(),
                render_time=S.Float()),
            **kw)


class ACE(S.Object):
    '''
    Access Control Entry

    :var access: either ``ACE.ALLOW`` or ``ACE.DENY``
    :var str reason: optional, user-entered text
    :var role_id: _id for a :class:`~allura.model.auth.ProjectRole`
    :var str permission: e.g. 'read', 'create', etc
    '''

    ALLOW, DENY = 'ALLOW', 'DENY'

    def __init__(self, permissions, **kwargs):
        if permissions is None:
            permission = S.String()
        else:
            permission = S.OneOf('*', *permissions)
        super().__init__(
            fields=dict(
                access=S.OneOf(self.ALLOW, self.DENY),
                reason=S.String(),
                role_id=S.ObjectId(),
                permission=permission),
            **kwargs)

    @classmethod
    def allow(cls, role_id, permission, reason=None):
        return Object(
            access=cls.ALLOW,
            reason=reason,
            role_id=role_id,
            permission=permission)

    @classmethod
    def deny(cls, role_id, permission, reason=None):
        ace = Object(
            access=cls.DENY,
            reason=reason,
            role_id=role_id,
            permission=permission)
        return ace

    @classmethod
    def match(cls, ace, role_id, permission):
        return (
            ace.role_id in (role_id, EVERYONE)
            and ace.permission in (permission, ALL_PERMISSIONS))


class ACL(S.Array):
    '''
    Access Control List.  Is an array of :class:`ACE`
    '''

    def __init__(self, permissions=None, **kwargs):
        super().__init__(
            field_type=ACE(permissions), **kwargs)

    @classmethod
    def contains(cls, ace, acl):
        """Test membership of ace in acl ignoring ace.reason field.

        Return actual ACE with reason filled if ace is found in acl, None otherwise

        e.g. `ACL.contains(ace, acl)` will return `{role_id=ObjectId(...), permission='read', access='DENY', reason='Spammer'}`
        with following vars:

        ace = M.ACE.deny(role_id, 'read')  # reason = None
        acl = [{role_id=ObjectId(...), permission='read', access='DENY', reason='Spammer'}]
        """
        def clear_reason(ace):
            return Object(access=ace.access, role_id=ace.role_id, permission=ace.permission)

        ace_without_reason = clear_reason(ace)
        for a in acl:
            if clear_reason(a) == ace_without_reason:
                return a

DENY_ALL = ACE.deny(EVERYONE, ALL_PERMISSIONS)
