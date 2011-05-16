from ming.orm.ormsession import ThreadLocalORMSession
from ming import schema
from nose.tools import raises, assert_raises

from forgetracker.model import Ticket
from forgetracker.tests.unit import TrackerTestWithModel


class TestTicketModel(TrackerTestWithModel):
    def test_that_it_has_ordered_custom_fields(self):
        custom_fields = dict(my_field='my value')
        Ticket(summary='my ticket', custom_fields=custom_fields, ticket_num=3)
        ThreadLocalORMSession.flush_all()
        ticket = Ticket.query.get(summary='my ticket')
        assert ticket.custom_fields == dict(my_field='my value')

    @raises(schema.Invalid)
    def test_ticket_num_required(self):
        Ticket(summary='my ticket')

    def test_ticket_num_required2(self):
        try:
            Ticket(summary='my ticket')
        except schema.Invalid:
            pass
        else:
            raise AssertionError('Expected schema.Invalid to be thrown')

    def test_private_ticket(self):
        from pylons import c
        from allura.model import ProjectRole, User
        from allura.model import ACE, ALL_PERMISSIONS, DENY_ALL
        from allura.lib.security import Credentials, has_access
        from allura.websetup import bootstrap

        admin = c.user
        creator = bootstrap.create_user('Not a Project Admin')
        developer = bootstrap.create_user('Project Developer')
        observer = bootstrap.create_user('Random Non-Project User')
        anon = User(_id=None, username='*anonymous',
                    display_name='Anonymous Coward')
        t = Ticket(summary='my ticket', ticket_num=3, reported_by_id=creator._id)

        assert creator == t.reported_by
        role_admin = ProjectRole.by_name('Admin')._id
        role_developer = ProjectRole.by_name('Developer')._id
        role_creator = t.reported_by.project_role()._id
        developer.project_role().roles.append(role_developer)
        cred = Credentials.get().clear()

        t.private = True
        assert t.acl == [ACE.allow(role_developer, ALL_PERMISSIONS),
                         ACE.allow(role_creator, ALL_PERMISSIONS),
                         DENY_ALL]
        assert has_access(t, 'read', user=admin)()
        assert has_access(t, 'write', user=admin)()
        assert has_access(t, 'read', user=creator)()
        assert has_access(t, 'write', user=creator)()
        assert has_access(t, 'read', user=developer)()
        assert has_access(t, 'write', user=developer)()
        assert not has_access(t, 'read', user=observer)()
        assert not has_access(t, 'write', user=observer)()
        assert not has_access(t, 'read', user=anon)()
        assert not has_access(t, 'write', user=anon)()

        t.private = False
        assert t.acl == []
        assert has_access(t, 'read', user=admin)()
        assert has_access(t, 'write', user=admin)()
        assert has_access(t, 'read', user=developer)()
        assert has_access(t, 'write', user=developer)()
        assert has_access(t, 'read', user=creator)()
        assert has_access(t, 'unmoderated_post', user=creator)()
        assert not has_access(t, 'write', user=creator)()
        assert has_access(t, 'read', user=observer)()
        assert has_access(t, 'read', user=anon)()
