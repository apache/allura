import pkg_resources
import unittest

from pylons import app_globals as g
from pylons import tmpl_context as c

from alluratest.controller import TestController, setup_basic_test, setup_global_objects
from allura.tests import decorators as td
from allura.lib import helpers as h
from allura import model as M

from forgegit.tests import with_git
from forgewiki import model as WM
from forgetracker import model as TM
from forgeorganization.organization.model import Organization, Membership, ProjectInvolvement

from ming.orm.ormsession import ThreadLocalORMSession

class TestStats(TestController):

    def setUp(self):
        super(TestStats, self).setUp()
        self.user1 = M.User.by_username('test-user')
        self.user2 = M.User.by_username('test-admin')
        self.user3 = M.User.by_username('test-user-1')
        self.organization = Organization.register(
            'testorg', 'Test Organization', 'For-profit business', self.user1)
        self.organization.project().add_user(self.user1, ['Admin'])
        self.organization.project().add_user(self.user2, ['Admin'])

        self.m1 = Membership.insert('Developer', 'closed', 
            self.organization._id, self.user1._id)
        self.m2 = Membership.insert('Developer', 'active', 
            self.organization._id, self.user2._id)
        self.m3 = Membership.insert('Developer', 'active', 
            self.organization._id, self.user3._id)

        self.project = M.Project.query.get(shortname='test')
        self.project.add_user(self.user1, ['Admin'])
        self.project.add_user(self.user2, ['Admin'])
        self.project.add_user(self.user3, ['Admin'])
        pi = ProjectInvolvement.insert('active', 'cooperation', 
            self.organization._id, self.project._id)

    @td.with_tool('test', 'wiki', mount_point='wiki', mount_label='wiki', username='test-admin')
    def test_wiki_stats(self):

        initial_artifacts = self.organization.stats.getArtifacts()
        initial_wiki = self.organization.stats.getArtifacts(art_type="Wiki")

        #Try to create a new page as a user enrolled in the organization which
        #is developing the project
        self.app.post('/wiki/newtestpage/update', 
            params=dict(title='newtestpage', text='footext'),
            extra_environ=dict(username=str(self.user2.username)))

        artifacts = self.organization.stats.getArtifacts()
        wiki = self.organization.stats.getArtifacts(art_type="Wiki")

        assert artifacts['created'] == 1 + initial_artifacts['created']
        assert artifacts['modified'] == initial_artifacts['modified']
        assert wiki['created'] == 1 + initial_wiki['created']
        assert wiki['modified'] == initial_wiki['modified']

        #Try to create a new page as another user enrolled in the organization
        #which is developing the project
        self.app.post('/wiki/newtestpage2/update', 
            params=dict(title='newtestpage2', text='footext2'),
            extra_environ=dict(username=str(self.user3.username)))

        artifacts = self.organization.stats.getArtifacts()
        wiki = self.organization.stats.getArtifacts(art_type="Wiki")

        assert artifacts['created'] == 2 + initial_artifacts['created']
        assert artifacts['modified'] == initial_artifacts['modified']
        assert wiki['created'] == 2 + initial_wiki['created']
        assert wiki['modified'] == initial_wiki['modified']

        #Try to edit a page as a user enrolled in the organization which
        #is developing the project
        self.app.post('/wiki/newtestpage2/update', 
            params=dict(title='newtestpage2', text='newcontent'),
            extra_environ=dict(username=str(self.user2.username)))

        artifacts = self.organization.stats.getArtifacts()
        wiki = self.organization.stats.getArtifacts(art_type="Wiki")

        assert artifacts['created'] == 2 + initial_artifacts['created']
        assert artifacts['modified'] == 1 + initial_artifacts['modified']
        assert wiki['created'] == 2 + initial_wiki['created']
        assert wiki['modified'] == 1 + initial_wiki['modified']

        #Try to create a new page as a user whose enrollment within the 
        #organization has been marked as closed
        self.app.post('/wiki/newtestpage3/update', 
            params=dict(title='newtestpage3', text='footext'),
            extra_environ=dict(username=str(self.user1.username)))

        artifacts = self.organization.stats.getArtifacts()
        wiki = self.organization.stats.getArtifacts(art_type="Wiki")

        assert artifacts['created'] == 2 + initial_artifacts['created']
        assert artifacts['modified'] == 1 + initial_artifacts['modified']
        assert wiki['created'] == 2 + initial_wiki['created']
        assert wiki['modified'] == 1 + initial_wiki['modified']

        #Try to edit an existing page as a user whose enrollment within the 
        #organization has been marked as closed
        self.app.post('/wiki/newtestpage/update', 
            params=dict(title='newtestpage', text='footext2'),
            extra_environ=dict(username=str(self.user1.username)))

        artifacts = self.organization.stats.getArtifacts()
        wiki = self.organization.stats.getArtifacts(art_type="Wiki")

        assert artifacts['created'] == 2 + initial_artifacts['created']
        assert artifacts['modified'] == 1 + initial_artifacts['modified']
        assert wiki['created'] == 2 + initial_wiki['created']
        assert wiki['modified'] == 1 + initial_wiki['modified']

    @td.with_tool('test', 'tickets', mount_point='tickets', mount_label='tickets', username='test-admin')
    def test_tracker_stats(self):

        initial_tickets = self.organization.stats.getTickets()
        initial_tickets_artifacts = self.organization.stats.getArtifacts(art_type="Ticket")

        r = self.app.post('/tickets/save_ticket', 
            params={'ticket_form.summary':'footext2',
                    'ticket_form.assigned_to' : str(self.user2.username)},
            extra_environ=dict(username=str(self.user2.username)))

        tickets = self.organization.stats.getTickets()
        tickets_artifacts = self.organization.stats.getArtifacts(art_type="Ticket")

        assert tickets['assigned'] == initial_tickets['assigned'] + 1
        assert tickets['solved'] == initial_tickets['solved']
        assert tickets['revoked'] == initial_tickets['revoked']
        assert tickets_artifacts['created'] == initial_tickets_artifacts['created'] + 1
        assert tickets_artifacts['modified'] == initial_tickets_artifacts['modified']

        r = self.app.post('/tickets/save_ticket', 
            params={'ticket_form.summary':'footext3',
                    'ticket_form.assigned_to' : str(self.user1.username)},
            extra_environ=dict(username=str(self.user2.username)))

        tickets = self.organization.stats.getTickets()
        tickets_artifacts = self.organization.stats.getArtifacts(art_type="Ticket")

        assert tickets['assigned'] == initial_tickets['assigned'] + 1
        assert tickets['solved'] == initial_tickets['solved']
        assert tickets['revoked'] == initial_tickets['revoked']
        assert tickets_artifacts['created'] == initial_tickets_artifacts['created'] + 2
        assert tickets_artifacts['modified'] == initial_tickets_artifacts['modified']

        ticket2num = str(TM.Ticket.query.get(summary='footext3').ticket_num)
        r = self.app.post('/tickets/%s/update_ticket_from_widget' % ticket2num, 
            params={'ticket_form.ticket_num' : ticket2num,
                    'ticket_form.summary':'footext3',
                    'ticket_form.assigned_to' : str(self.user3.username)},
            extra_environ=dict(username=str(self.user2.username)))

        tickets = self.organization.stats.getTickets()
        tickets_artifacts = self.organization.stats.getArtifacts(art_type="Ticket")

        assert tickets['assigned'] == initial_tickets['assigned'] + 2
        assert tickets['solved'] == initial_tickets['solved']
        assert tickets['revoked'] == initial_tickets['revoked']
        assert tickets_artifacts['created'] == initial_tickets_artifacts['created'] + 2
        assert tickets_artifacts['modified'] == initial_tickets_artifacts['modified'] + 1
 
        r = self.app.post('/tickets/%s/update_ticket_from_widget' % ticket2num, 
            params={'ticket_form.ticket_num' : ticket2num,
                    'ticket_form.summary':'footext2',
                    'ticket_form.status':'closed',
                    'ticket_form.assigned_to' : str(self.user3.username)},
            extra_environ=dict(username=str(self.user2.username)))

        tickets = self.organization.stats.getTickets()
        tickets_artifacts = self.organization.stats.getArtifacts(art_type="Ticket")

        assert tickets['assigned'] == initial_tickets['assigned'] + 2
        assert tickets['solved'] == initial_tickets['solved'] + 1
        assert tickets['revoked'] == initial_tickets['revoked']
        assert tickets_artifacts['created'] == initial_tickets_artifacts['created'] + 2
        assert tickets_artifacts['modified'] == initial_tickets_artifacts['modified'] + 2

        ticket1num = str(TM.Ticket.query.get(summary='footext2').ticket_num)
        r = self.app.post('/tickets/%s/update_ticket_from_widget' % ticket1num, 
            params={'ticket_form.ticket_num' : ticket1num,
                    'ticket_form.summary':'footext2',
                    'ticket_form.status':'closed',
                    'ticket_form.assigned_to' : str(self.user1.username)},
            extra_environ=dict(username=str(self.user2.username)))

        tickets = self.organization.stats.getTickets()
        tickets_artifacts = self.organization.stats.getArtifacts(art_type="Ticket")

        assert tickets['assigned'] == initial_tickets['assigned'] + 2
        assert tickets['solved'] == initial_tickets['solved'] + 1
        assert tickets['revoked'] == initial_tickets['revoked'] + 1
        assert tickets_artifacts['created'] == initial_tickets_artifacts['created'] + 2
        assert tickets_artifacts['modified'] == initial_tickets_artifacts['modified'] + 3

class TestGitCommitActiveMember(unittest.TestCase, TestController):

    def setUp(self):
        setup_basic_test()
        self.user = M.User.by_username('test-admin')
        self.organization = Organization.register(
            'testorg', 'Test Organization', 'For-profit business', self.user)
        self.organization.project().add_user(self.user, ['Admin'])

        self.m = Membership.insert('Developer', 'active', 
            self.organization._id, self.user._id)
        
        self.project = M.Project.query.get(shortname='test')
        self.project.add_user(self.user, ['Admin'])
        pi = ProjectInvolvement.insert('active', 'cooperation', 
            self.organization._id, self.project._id)
        addr = M.EmailAddress.upsert('rcopeland@geek.net')
        self.user.claim_address('rcopeland@geek.net')
        self.setup_with_tools()

    @with_git
    @td.with_wiki
    def setup_with_tools(self):
        setup_global_objects()
        h.set_context('test', 'src-git', neighborhood='Projects')
        repo_dir = pkg_resources.resource_filename(
            'forgeuserstats', 'tests/data')
        c.app.repo.fs_path = repo_dir
        c.app.repo.name = 'testgit.git'
        self.repo = c.app.repo
        self.repo.refresh()
        self.rev = M.repo.Commit.query.get(_id=self.repo.heads[0]['object_id'])
        self.rev.repo = self.repo

    @td.with_user_project('test-admin')
    def test_commit_member(self):
        commits = self.organization.stats.getCommits()
        assert commits['number'] == 4
        lmcommits = self.organization.stats.getLastMonthCommits()
        assert lmcommits['number'] == 4

class TestGitCommitPastMember(unittest.TestCase, TestController):

    def setUp(self):
        setup_basic_test()
        self.user = M.User.by_username('test-admin')
        self.organization = Organization.register(
            'testorg', 'Test Organization', 'For-profit business', self.user)
        self.organization.project().add_user(self.user, ['Admin'])
        self.m = Membership.insert('Developer', 'closed', 
            self.organization._id, self.user._id)
        
        self.project = M.Project.query.get(shortname='test')
        self.project.add_user(self.user, ['Admin'])
        pi = ProjectInvolvement.insert('active', 'cooperation', 
            self.organization._id, self.project._id)
        addr = M.EmailAddress.upsert('rcopeland@geek.net')
        self.user.claim_address('rcopeland@geek.net')
        self.setup_with_tools()

    @with_git
    @td.with_wiki
    def setup_with_tools(self):
        setup_global_objects()
        h.set_context('test', 'src-git', neighborhood='Projects')
        repo_dir = pkg_resources.resource_filename(
            'forgeuserstats', 'tests/data')
        c.app.repo.fs_path = repo_dir
        c.app.repo.name = 'testgit.git'
        self.repo = c.app.repo
        self.repo.refresh()
        self.rev = M.repo.Commit.query.get(_id=self.repo.heads[0]['object_id'])
        self.rev.repo = self.repo

    @td.with_user_project('test-admin')
    def test_commit_member(self):
        commits = self.organization.stats.getCommits()
        assert commits['number'] == 0
        lmcommits = self.organization.stats.getLastMonthCommits()
        assert lmcommits['number'] == 0
