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

from tg import tmpl_context as c
from datetime import datetime
import six.moves.urllib.parse
import six.moves.urllib.request
import six.moves.urllib.error

import mock
import pytest
from ming.orm.ormsession import ThreadLocalORMSession
from ming.orm import session
from ming import schema
from forgetracker.model import Ticket, TicketAttachment
from forgetracker.tests.unit import TrackerTestWithModel
from forgetracker.import_support import ResettableStream
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
        label_count1 = t1.artifacts_labeled_with(
            "mylabel", t1.app_config).count()
        label_count2 = t2.artifacts_labeled_with(
            "mylabel", t2.app_config).count()
        assert 1 == label_count1 == label_count2

    def test_that_it_has_ordered_custom_fields(self):
        custom_fields = dict(my_field='my value')
        Ticket(summary='my ticket', custom_fields=custom_fields, ticket_num=3)
        ThreadLocalORMSession.flush_all()
        ticket = Ticket.query.get(summary='my ticket')
        assert ticket.custom_fields == dict(my_field='my value')

    def test_ticket_num_required(self):
        with pytest.raises(schema.Invalid):
            Ticket(summary='my ticket')

    def test_ticket_num_required2(self):
        t = Ticket(summary='my ticket', ticket_num=12)
        try:
            t.ticket_num = None
        except schema.Invalid:
            pass
        else:
            raise AssertionError('Expected schema.Invalid to be thrown')

    def test_activity_extras(self):
        t = Ticket(summary='my ticket', ticket_num=12)
        assert 'allura_id' in t.activity_extras
        assert t.activity_extras['summary'] == t.summary

    def test_has_activity_access(self):
        t = Ticket(summary='ticket', ticket_num=666)
        assert t.has_activity_access('read', c.user, 'activity')
        t.deleted = True
        assert not t.has_activity_access('read', c.user, 'activity')

    def test_comment_has_activity_access(self):
        t = Ticket(summary='ticket', ticket_num=666, deleted=True)
        p = t.discussion_thread.add_post(text='test post')
        assert p.status == 'ok'
        assert p.has_activity_access('read', c.user, 'activity')
        p.status = 'spam'
        assert not p.has_activity_access('read', c.user, 'activity')
        p.status = 'pending'
        assert not p.has_activity_access('read', c.user, 'activity')
        p.status = 'ok'
        p.deleted = True
        assert not p.has_activity_access('read', c.user, 'activity')

    def test_private_ticket(self):
        from allura.model import ProjectRole
        from allura.model import ACE, DENY_ALL
        from allura.lib.security import Credentials, has_access
        from allura.websetup import bootstrap

        admin = c.user
        creator = bootstrap.create_user('Not a Project Admin')
        developer = bootstrap.create_user('Project Developer')
        observer = bootstrap.create_user('Random Non-Project User')
        anon = User(_id=None, username='*anonymous',
                    display_name='Anonymous')
        t = Ticket(summary='my ticket', ticket_num=3,
                   reported_by_id=creator._id)

        assert creator == t.reported_by
        role_admin = ProjectRole.by_name('Admin')._id
        role_developer = ProjectRole.by_name('Developer')._id
        role_creator = ProjectRole.by_user(t.reported_by, upsert=True)._id
        ProjectRole.by_user(
            developer, upsert=True).roles.append(role_developer)
        ThreadLocalORMSession.flush_all()
        cred = Credentials.get().clear()

        t.private = True
        assert t.acl == [
            ACE.allow(role_developer, 'create'),
            ACE.allow(role_developer, 'delete'),
            ACE.allow(role_developer, 'moderate'),
            ACE.allow(role_developer, 'post'),
            ACE.allow(role_developer, 'read'),
            ACE.allow(role_developer, 'save_searches'),
            ACE.allow(role_developer, 'unmoderated_post'),
            ACE.allow(role_developer, 'update'),
            ACE.allow(role_creator, 'create'),
            ACE.allow(role_creator, 'post'),
            ACE.allow(role_creator, 'read'),
            ACE.allow(role_creator, 'unmoderated_post'),
            DENY_ALL]
        assert has_access(t, 'read', user=admin)()
        assert has_access(t, 'create', user=admin)()
        assert has_access(t, 'update', user=admin)()
        assert has_access(t, 'read', user=creator)()
        assert has_access(t, 'post', user=creator)()
        assert has_access(t, 'unmoderated_post', user=creator)()
        assert has_access(t, 'create', user=creator)()
        assert not has_access(t, 'update', user=creator)()
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
        assert has_access(t, 'create', user=creator)()
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
        assert t.created_date == datetime(2012, 10, 29, 9, 57, 21, 465000)
        f = Feed.post(
            t,
            title=t.summary,
            description=t.description,
            pubdate=t.created_date)
        assert f.pubdate == datetime(2012, 10, 29, 9, 57, 21, 465000)
        assert f.title == 'test ticket'
        assert (f.description ==
                     '<div class="markdown_content"><p>test description</p></div>')

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

        assert (
            Ticket.query.find({'app_config_id': app1.config._id}).count() == 1)
        assert (
            Ticket.query.find({'app_config_id': app2.config._id}).count() == 0)
        assert (
            Post.query.find(dict(thread_id=ticket.discussion_thread._id)).count() == 1)

        t = ticket.move(app2.config)
        assert (
            Ticket.query.find({'app_config_id': app1.config._id}).count() == 0)
        assert (
            Ticket.query.find({'app_config_id': app2.config._id}).count() == 1)
        assert t.summary == 'test ticket'
        assert t.description == 'test description'
        assert t.assigned_to.username == 'test-user'
        assert t.url() == '/p/test/bugs2/1/'

        post = Post.query.find(dict(thread_id=ticket.discussion_thread._id,
                                    text={'$ne': 'test comment'})).first()
        assert post is not None, 'No comment about ticket moving'
        message = 'Ticket moved from /p/test/bugs/1/'
        assert post.text == message

        post = Post.query.find(dict(text='test comment')).first()
        assert post.thread.discussion_id == app2.config.discussion_id
        assert post.thread.app_config_id == app2.config._id
        assert post.app_config_id == app2.config._id

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
        assert t.summary == 'test ticket'
        assert t.description == 'test description'
        assert t.custom_fields['_test'] == 'test val'
        post = Post.query.find(
            dict(thread_id=ticket.discussion_thread._id)).first()
        assert post is not None, 'No comment about ticket moving'
        message = 'Ticket moved from /p/test/bugs/1/'
        message += '\n\nCan\'t be converted:\n'
        message += '\n- **_test2**: test val 2'
        assert post.text == message

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
            # not in project
            ticket.custom_fields['_user_field_2'] = 'test-user-0'
            # not in project
            ticket.assigned_to_id = User.by_username('test-user-0')._id

        t = ticket.move(app2.config)
        assert t.assigned_to_id is None
        assert t.custom_fields['_user_field'] == 'test-user'
        assert t.custom_fields['_user_field_2'] == ''
        post = Post.query.find(
            dict(thread_id=ticket.discussion_thread._id)).first()
        assert post is not None, 'No comment about ticket moving'
        message = 'Ticket moved from /p/test/bugs/1/'
        message += '\n\nCan\'t be converted:\n'
        message += '\n- **_user_field_2**: test-user-0 (user not in project)'
        message += '\n- **assigned_to**: test-user-0 (user not in project)'
        assert post.text == message

    @td.with_tool('test', 'Tickets', 'bugs', username='test-user')
    def test_attach_with_resettable_stream(self):
        with h.push_context(c.project._id, app_config_id=c.app.config._id):
            ticket = Ticket.new()
            ticket.summary = 'test ticket'
            ticket.description = 'test description'
        assert len(ticket.attachments) == 0
        f = six.moves.urllib.request.urlopen('file://%s' % __file__)
        TicketAttachment.save_attachment(
            'test_ticket_model.py', ResettableStream(f),
            artifact_id=ticket._id)
        ThreadLocalORMSession.flush_all()
        # need to refetch since attachments are cached
        session(ticket).expunge(ticket)
        ticket = Ticket.query.get(_id=ticket._id)
        assert len(ticket.attachments) == 1
        assert ticket.attachments[0].filename == 'test_ticket_model.py'

    def test_json_parents(self):
        ticket = Ticket.new()
        json_keys = list(ticket.__json__().keys())
        assert 'related_artifacts' in json_keys  # from Artifact
        assert 'votes_up' in json_keys  # VotableArtifact
        assert 'ticket_num' in json_keys  # Ticket
        assert ticket.__json__()['assigned_to'] is None

    @mock.patch('forgetracker.model.ticket.tsearch')
    @mock.patch.object(Ticket, 'paged_search')
    @mock.patch.object(Ticket, 'paged_query')
    def test_paged_query_or_search(self, query, search, tsearch):
        app_cfg, user = mock.Mock(), mock.Mock()
        mongo_query = 'mongo query'
        solr_query = 'solr query'
        kw = {'kw1': 'test1', 'kw2': 'test2'}
        filter = None
        Ticket.paged_query_or_search(app_cfg, user, mongo_query, solr_query, filter, **kw)
        query.assert_called_once_with(app_cfg, user, mongo_query, sort=None, limit=None, page=0, **kw)
        assert tsearch.query_filter_choices.call_count == 1
        assert tsearch.query_filter_choices.call_args[0][0] == 'solr query'
        assert search.call_count == 0
        query.reset_mock(), search.reset_mock(), tsearch.reset_mock()

        filter = {'status': 'unread'}
        Ticket.paged_query_or_search(app_cfg, user, mongo_query, solr_query, filter, **kw)
        search.assert_called_once_with(app_cfg, user, solr_query, filter=filter, sort=None, limit=None, page=0, **kw)
        assert query.call_count == 0
        assert tsearch.query_filter_choices.call_count == 0

    def test_index(self):
        idx = Ticket(ticket_num=2, summary="ticket2", labels=["mylabel", "other"]).index()
        assert idx['summary_t'] == 'ticket2'
        assert idx['labels_t'] == 'mylabel other'
        assert idx['reported_by_s'] == 'test-user'
        assert idx['assigned_to_s'] is None  # must exist at least
