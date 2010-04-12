from pylons import g
from formencode.variabledecode import variable_encode

from ming.orm.ormsession import ThreadLocalORMSession

from pyforge.tests import TestController
from pyforge import model as M

class TestFeeds(TestController):

    def setUp(self):
        TestController.setUp(self)
        self.app.get('/wiki/')
        self.app.get('/tickets/')
        r = self.app.post(
            '/tickets/save_ticket',
            params=variable_encode(dict(
                    ticket_form=dict(
                    ticket_num='',
                    tags='',
                    labels='',
                    assigned_to='',
                    milestone='',
                    summary='This is a ticket',
                    status='open',
                    description='This is a description'))),
            status=302)

    def test_project_feed(self):
        self.app.get('/feed.rss')
        self.app.get('/feed.atom')

    def test_wiki_feed(self):
        self.app.get('/wiki/feed.rss')
        self.app.get('/wiki/feed.atom')

    def test_wiki_page_feed(self):
        self.app.get('/wiki/Root/feed.rss')
        self.app.get('/wiki/Root/feed.atom')

    def test_ticket_list_feed(self):
        self.app.get('/tickets/feed.rss')
        self.app.get('/tickets/feed.atom')

    def test_ticket_feed(self):
        self.app.get('/tickets/1/feed.rss')
        r = self.app.get('/tickets/1/feed.atom')
        assert 'created' in r
        self.app.post('/tickets/1/update_ticket', params=dict(
                assigned_to='',
                ticket_num='',
                labels='',
                labels_old='',
                tags='',
                tags_old='',
                summary='This is a new ticket',
                status='unread',
                milestone='',
                description='This is another description'))
        r = self.app.get('/tickets/1/feed.atom')
        assert '=&gt;' in r
        assert '&lt;ins&gt;' in r

