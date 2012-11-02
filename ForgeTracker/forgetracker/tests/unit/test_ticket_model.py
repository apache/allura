from pylons import c
from datetime import datetime

from ming.orm.ormsession import ThreadLocalORMSession
from ming import schema
from nose.tools import raises, assert_raises, assert_equal

from forgetracker.model import Ticket
from forgetracker.tests.unit import TrackerTestWithModel
from allura.model import Feed


class TestTicketModel(TrackerTestWithModel):
    def test_that_label_counts_are_local_to_tool(self):
        """Test that label queries return only artifacts from the specified
        tool.
        """
        # create a ticket in two different tools, with the same label
        from allura.tests import decorators as td
        @td.with_tool('test', 'Tickets', 'bugs', username='test-user')
        def _test_ticket():
            return Ticket(ticket_num=1, summary="ticket1", labels=["mylabel"])

        @td.with_tool('test', 'Tickets', 'bugs2', username='test-user')
        def _test_ticket2():
            return Ticket(ticket_num=2, summary="ticket2", labels=["mylabel"])

        # create and save the tickets
        t1 = _test_ticket()
        t2 = _test_ticket2()
        ThreadLocalORMSession.flush_all()

        # test label query results
        label_count1 = t1.artifacts_labeled_with("mylabel", t1.app_config).count()
        label_count2 = t2.artifacts_labeled_with("mylabel", t2.app_config).count()
        assert 1 == label_count1 == label_count2

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
        t = Ticket(summary='my ticket', ticket_num=12)
        try:
            t.ticket_num = None
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
                    display_name='Anonymous')
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
        assert has_access(t, 'create', user=admin)()
        assert has_access(t, 'update', user=admin)()
        assert has_access(t, 'read', user=creator)()
        assert has_access(t, 'create', user=creator)()
        assert has_access(t, 'update', user=creator)()
        assert has_access(t, 'read', user=developer)()
        assert has_access(t, 'create', user=developer)()
        assert has_access(t, 'update', user=developer)()
        assert not has_access(t, 'read', user=observer)()
        assert not has_access(t, 'create', user=observer)()
        assert not has_access(t, 'update', user=observer)()
        assert not has_access(t, 'read', user=anon)()
        assert not has_access(t, 'create', user=anon)()
        assert not has_access(t, 'update', user=anon)()

        t.private = False
        assert t.acl == []
        assert has_access(t, 'read', user=admin)()
        assert has_access(t, 'create', user=admin)()
        assert has_access(t, 'update', user=admin)()
        assert has_access(t, 'read', user=developer)()
        assert has_access(t, 'create', user=developer)()
        assert has_access(t, 'update', user=developer)()
        assert has_access(t, 'read', user=creator)()
        assert has_access(t, 'unmoderated_post', user=creator)()
        assert not has_access(t, 'create', user=creator)()
        assert not has_access(t, 'update', user=creator)()
        assert has_access(t, 'read', user=observer)()
        assert has_access(t, 'read', user=anon)()

    def test_feed(self):
        t = Ticket(
        app_config_id=c.app.config._id,
        ticket_num=1,
        summary='test ticket',
        description='test description',
        created_date=datetime(2012, 10, 29, 9, 57, 21, 465000))
        assert_equal(t.created_date, datetime(2012, 10, 29, 9, 57, 21, 465000))
        f = Feed.post(
            t,
            title=t.summary,
            description=t.description,
            pubdate=t.created_date)
        assert_equal(f.pubdate, datetime(2012, 10, 29, 9, 57, 21, 465000))
        assert_equal(f.title, 'test ticket')
        assert_equal(f.description, 'test description')
