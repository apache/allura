from pylons import g
from formencode.variabledecode import variable_encode

from ming.orm.ormsession import ThreadLocalORMSession

from pyforge.tests import TestController
from pyforge import model as M

class TestFeeds(TestController):

    def setUp(self):
        TestController.setUp(self)
        self.app.get('/Wiki/')
        self.app.get('/Tickets/')
        self.app.post('/Tickets/save_ticket', params=dict(
                ticket_num='',
                tags='',
                summary='This is a ticket',
                status='open',
                description='This is a description'))

    def test_project_feed(self):
        self.app.get('/feed.rss')
        self.app.get('/feed.xml')

    def test_wiki_feed(self):
        self.app.get('/Wiki/feed.rss')
        self.app.get('/Wiki/feed.xml')

    def test_wiki_page_feed(self):
        self.app.get('/Wiki/Root/feed.rss')
        self.app.get('/Wiki/Root/feed.xml')

    def test_ticket_list_feed(self):
        self.app.get('/Tickets/feed.rss')
        self.app.get('/Tickets/feed.xml')

    def test_ticket_feed(self):
        self.app.get('/Tickets/1/feed.rss')
        self.app.get('/Tickets/1/feed.xml')
