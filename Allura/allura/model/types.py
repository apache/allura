from ming.base import Object
from ming import schema as S

EVERYONE, ALL_PERMISSIONS = None, '*'

class ACE(S.Object):
    '''ACE - access control entry'''
    ALLOW, DENY = 'ALLOW', 'DENY'
    def __init__(self, permissions, **kwargs):
        if permissions is None:
            permission=S.String()
        else:
            permission=S.OneOf('*', *permissions)
        super(ACE, self).__init__(
            fields=dict(
                access=S.OneOf(self.ALLOW, self.DENY),
                role_id=S.ObjectId(),
                permission=permission),
            **kwargs)

    @classmethod
    def allow(cls, role_id, permission):
        return Object(
            access=cls.ALLOW,
            role_id=role_id,
            permission=permission)

    @classmethod
    def deny(cls, role_id, permission):
        return Object(
            access=cls.DENY,
            role_id=role_id,
            permission=permission)

    @classmethod
    def match(cls, ace, role_id, permission):
        return (
            ace.role_id in (role_id, EVERYONE)
            and ace.permission in (permission, ALL_PERMISSIONS))

class ACL(S.Array):

    def __init__(self, permissions=None, **kwargs):
        super(ACL, self).__init__(
            field_type=ACE(permissions), **kwargs)

DENY_ALL = ACE.deny(EVERYONE, ALL_PERMISSIONS)
