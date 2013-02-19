from pylons import tmpl_context as c
from datetime import datetime

from ming.orm.ormsession import ThreadLocalORMSession
from ming import schema
from nose.tools import raises, assert_raises, assert_equal

from forgetracker.model import Ticket
from forgetracker.tests.unit import TrackerTestWithModel
from allura.model import Feed, Post, User
from allura.lib import helpers as h
from allura.tests import decorators as td


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
        from pylons import tmpl_context as c
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
        ThreadLocalORMSession.flush_all()
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
        assert_equal(f.description, '<div class="markdown_content"><p>test description</p></div>')

    @td.with_tool('test', 'Tickets', 'bugs', username='test-user')
    @td.with_tool('test', 'Tickets', 'bugs2', username='test-user')
    def test_ticket_move(self):
        app1 = c.project.app_instance('bugs')
        app2 = c.project.app_instance('bugs2')
        with h.push_context(c.project._id, app_config_id=app1.config._id):
            ticket = Ticket.new()
            ticket.summary = 'test ticket'
            ticket.description = 'test description'
            ticket.assigned_to_id = User.by_username('test-user')._id
            ticket.discussion_thread.add_post(text='test comment')

        assert_equal(Ticket.query.find({'app_config_id': app1.config._id}).count(), 1)
        assert_equal(Ticket.query.find({'app_config_id': app2.config._id}).count(), 0)
        assert_equal(Post.query.find(dict(thread_id=ticket.discussion_thread._id)).count(), 1)

        t = ticket.move(app2.config)
        assert_equal(Ticket.query.find({'app_config_id': app1.config._id}).count(), 0)
        assert_equal(Ticket.query.find({'app_config_id': app2.config._id}).count(), 1)
        assert_equal(t.summary, 'test ticket')
        assert_equal(t.description, 'test description')
        assert_equal(t.assigned_to.username, 'test-user')
        assert_equal(t.url(), '/p/test/bugs2/1/')

        post = Post.query.find(dict(thread_id=ticket.discussion_thread._id,
                                    text={'$ne': 'test comment'})).first()
        assert post is not None, 'No comment about ticket moving'
        message = 'Ticket moved from /p/test/bugs/1/'
        assert_equal(post.text, message)

        post = Post.query.find(dict(text='test comment')).first()
        assert_equal(post.thread.discussion_id, app2.config.discussion_id)
        assert_equal(post.thread.app_config_id, app2.config._id)
        assert_equal(post.app_config_id, app2.config._id)

    @td.with_tool('test', 'Tickets', 'bugs', username='test-user')
    @td.with_tool('test', 'Tickets', 'bugs2', username='test-user')
    def test_ticket_move_with_different_custom_fields(self):
        app1 = c.project.app_instance('bugs')
        app2 = c.project.app_instance('bugs2')
        app1.globals.custom_fields.extend([
            {'name': '_test', 'type': 'string', 'label': 'Test field'},
            {'name': '_test2', 'type': 'string', 'label': 'Test field 2'}])
        app2.globals.custom_fields.append(
            {'name': '_test', 'type': 'string', 'label': 'Test field'})
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        with h.push_context(c.project._id, app_config_id=app1.config._id):
            ticket = Ticket.new()
            ticket.summary = 'test ticket'
            ticket.description = 'test description'
            ticket.custom_fields['_test'] = 'test val'
            ticket.custom_fields['_test2'] = 'test val 2'

        t = ticket.move(app2.config)
        assert_equal(t.summary, 'test ticket')
        assert_equal(t.description, 'test description')
        assert_equal(t.custom_fields['_test'], 'test val')
        post = Post.query.find(dict(thread_id=ticket.discussion_thread._id)).first()
        assert post is not None, 'No comment about ticket moving'
        message = 'Ticket moved from /p/test/bugs/1/'
        message += '\n\nCan\'t be converted:\n'
        message += '\n- **_test2**: test val 2'
        assert_equal(post.text, message)

    @td.with_tool('test', 'Tickets', 'bugs', username='test-user')
    @td.with_tool('test', 'Tickets', 'bugs2', username='test-user')
    def test_ticket_move_with_users_not_in_project(self):
        app1 = c.project.app_instance('bugs')
        app2 = c.project.app_instance('bugs2')
        app1.globals.custom_fields.extend([
            {'name': '_user_field', 'type': 'user', 'label': 'User field'},
            {'name': '_user_field_2', 'type': 'user', 'label': 'User field 2'}])
        app2.globals.custom_fields.extend([
            {'name': '_user_field', 'type': 'user', 'label': 'User field'},
            {'name': '_user_field_2', 'type': 'user', 'label': 'User field 2'}])
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        from allura.websetup import bootstrap
        bootstrap.create_user('test-user-0')
        with h.push_context(c.project._id, app_config_id=app1.config._id):
            ticket = Ticket.new()
            ticket.summary = 'test ticket'
            ticket.description = 'test description'
            ticket.custom_fields['_user_field'] = 'test-user'  # in project
            ticket.custom_fields['_user_field_2'] = 'test-user-0'  # not in project
            ticket.assigned_to_id = User.by_username('test-user-0')._id  # not in project

        t = ticket.move(app2.config)
        assert_equal(t.assigned_to_id, None)
        assert_equal(t.custom_fields['_user_field'], 'test-user')
        assert_equal(t.custom_fields['_user_field_2'], '')
        post = Post.query.find(dict(thread_id=ticket.discussion_thread._id)).first()
        assert post is not None, 'No comment about ticket moving'
        message = 'Ticket moved from /p/test/bugs/1/'
        message += '\n\nCan\'t be converted:\n'
        message += '\n- **_user_field_2**: test-user-0 (user not in project)'
        message += '\n- **assigned_to**: test-user-0 (user not in project)'
        assert_equal(post.text, message)
