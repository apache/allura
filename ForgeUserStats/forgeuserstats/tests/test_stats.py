import pkg_resources

from pylons import app_globals as g
from pylons import tmpl_context as c

from alluratest.controller import TestController
from allura.tests import decorators as td
from allura.lib import helpers as h
from allura.model import User

from forgewiki import model as WM
from forgetracker import model as TM

class TestStats(TestController):

    test_username = 'teststats'
    test_password = 'foo'

    def setUp(self):
        super(TestStats, self).setUp()
        for ep in pkg_resources.iter_entry_points("allura.stats"):
            if ep.name.lower() == 'userstats':
                g.statslisteners = [ep.load()().listener]

        self.user = User.register(dict(username=self.test_username,
            display_name='Test Stats'),
            make_project=False)
        self.user.set_password(self.test_password)
        
    def test_init_values(self):
        artifacts = self.user.stats.getArtifacts()
        tickets = self.user.stats.getTickets()
        commits = self.user.stats.getCommits()
        assert self.user.stats.tot_logins_count == 0
        assert artifacts['created'] == 0
        assert artifacts['modified'] == 0
        assert tickets['assigned'] == 0
        assert tickets['solved'] == 0
        assert tickets['revoked'] == 0
        assert tickets['averagesolvingtime'] is None
        assert commits['number'] == 0
        assert commits['lines'] == 0

        lmartifacts = self.user.stats.getLastMonthArtifacts()
        lmtickets = self.user.stats.getLastMonthTickets()
        lmcommits = self.user.stats.getLastMonthCommits()
        assert self.user.stats.getLastMonthLogins() == 0
        assert lmartifacts['created'] == 0
        assert lmartifacts['modified'] == 0
        assert lmtickets['assigned'] == 0
        assert lmtickets['solved'] == 0
        assert lmtickets['revoked'] == 0
        assert lmtickets['averagesolvingtime'] is None
        assert lmcommits['number'] == 0
        assert lmcommits['lines'] == 0

    def test_login(self):
        init_logins = self.user.stats.tot_logins_count
        r = self.app.post('/auth/do_login', params=dict(
                username=self.test_username, password=self.test_password))

        assert self.user.stats.tot_logins_count == 1 + init_logins
        assert self.user.stats.getLastMonthLogins() == 1 + init_logins

    @td.with_user_project('test-admin')
    @td.with_wiki
    def test_wiki_stats(self):
        initial_artifacts = c.user.stats.getArtifacts()
        initial_wiki = c.user.stats.getArtifacts(art_type="Wiki")

        h.set_context('test', 'wiki', neighborhood='Projects')
        page = WM.Page(title="TestPage", text="some text")
        page.commit()

        artifacts = c.user.stats.getArtifacts()
        wiki = c.user.stats.getArtifacts(art_type="Wiki")

        assert artifacts['created'] == 1 + initial_artifacts['created']
        assert artifacts['modified'] == initial_artifacts['modified']
        assert wiki['created'] == 1 + initial_wiki['created']
        assert wiki['modified'] == initial_wiki['modified']

        page = WM.Page(title="TestPage2", text="some different text")
        page.commit()

        artifacts = c.user.stats.getArtifacts()
        wiki = c.user.stats.getArtifacts(art_type="Wiki")

        assert artifacts['created'] == 2 + initial_artifacts['created']
        assert artifacts['modified'] == initial_artifacts['modified']
        assert wiki['created'] == 2 + initial_wiki['created']
        assert wiki['modified'] == initial_wiki['modified']


        page.text="some modified text"
        page.commit()

        artifacts = c.user.stats.getArtifacts()
        wiki = c.user.stats.getArtifacts(art_type="Wiki")

        assert artifacts['created'] == 2 + initial_artifacts['created']
        assert artifacts['modified'] == 1 + initial_artifacts['modified']
        assert wiki['created'] == 2 + initial_wiki['created']
        assert wiki['modified'] == 1 + initial_wiki['modified']


    @td.with_user_project('test-admin')
    @td.with_tracker
    def test_tracker_stats(self):
        initial_tickets = c.user.stats.getTickets()
        initial_tickets_artifacts = c.user.stats.getArtifacts(art_type="Ticket")

        h.set_context('test', 'bugs', neighborhood='Projects')
        ticket = TM.Ticket(ticket_num=12, summary="test", assigned_to_id = c.user._id)
        ticket.commit()

        tickets = c.user.stats.getTickets()
        tickets_artifacts = c.user.stats.getArtifacts(art_type="Ticket")

        assert tickets['assigned'] == initial_tickets['assigned'] + 1
        assert tickets['solved'] == initial_tickets['solved']
        assert tickets['revoked'] == initial_tickets['revoked']
        assert tickets_artifacts['created'] == initial_tickets_artifacts['created'] + 1
        assert tickets_artifacts['modified'] == initial_tickets_artifacts['modified']

        ticket.status = 'closed'
        ticket.commit()

        tickets = c.user.stats.getTickets()
        tickets_artifacts = c.user.stats.getArtifacts(art_type="Ticket")

        assert tickets['assigned'] == initial_tickets['assigned'] + 1
        assert tickets['solved'] == initial_tickets['solved'] + 1
        assert tickets['revoked'] == initial_tickets['revoked']
        assert tickets_artifacts['created'] == initial_tickets_artifacts['created'] + 1
        assert tickets_artifacts['modified'] == initial_tickets_artifacts['modified'] + 1

        h.set_context('test', 'bugs', neighborhood='Projects')
        ticket = TM.Ticket(ticket_num=13, summary="test")
        ticket.commit()
        
        tickets = c.user.stats.getTickets()
        tickets_artifacts = c.user.stats.getArtifacts(art_type="Ticket")

        assert tickets['assigned'] == initial_tickets['assigned'] + 1
        assert tickets['solved'] == initial_tickets['solved'] + 1
        assert tickets['revoked'] == initial_tickets['revoked']
        assert tickets_artifacts['created'] == initial_tickets_artifacts['created'] + 2
        assert tickets_artifacts['modified'] == initial_tickets_artifacts['modified'] + 1

        ticket.assigned_to_id = c.user._id
        ticket.commit()

        tickets = c.user.stats.getTickets()
        tickets_artifacts = c.user.stats.getArtifacts(art_type="Ticket")
        
        assert tickets['assigned'] == initial_tickets['assigned'] + 2
        assert tickets['solved'] == initial_tickets['solved'] + 1
        assert tickets['revoked'] == initial_tickets['revoked']
        assert tickets_artifacts['created'] == initial_tickets_artifacts['created'] + 2
        assert tickets_artifacts['modified'] == initial_tickets_artifacts['modified'] + 2

        ticket.assigned_to_id = self.user._id
        ticket.commit()

        tickets = c.user.stats.getTickets()
        tickets_artifacts = c.user.stats.getArtifacts(art_type="Ticket")
        
        assert tickets['assigned'] == initial_tickets['assigned'] + 2
        assert tickets['solved'] == initial_tickets['solved'] + 1
        assert tickets['revoked'] == initial_tickets['revoked'] + 1
        assert tickets_artifacts['created'] == initial_tickets_artifacts['created'] + 2
        assert tickets_artifacts['modified'] == initial_tickets_artifacts['modified'] + 3
