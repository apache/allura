from pylons import g
from formencode.variabledecode import variable_encode

from ming.orm.ormsession import ThreadLocalORMSession

from allura.tests import TestController
from allura import model as M

class TestFeeds(TestController):

    def setUp(self):
        TestController.setUp(self)
        self.app.get('/wiki/')
        self.app.get('/bugs/')
        self.app.post(
            '/bugs/save_ticket',
            params=variable_encode(dict(
                    ticket_form=dict(
                    ticket_num='',
                    labels='',
                    assigned_to='',
                    milestone='',
                    summary='This is a ticket',
                    status='open',
                    description='This is a description'))),
            status=302)
        title = u'Descri\xe7\xe3o e Arquitetura'.encode('utf-8')
        self.app.post(
            '/wiki/%s/update' % title,
            params=dict(
                title=title,
                text="Nothing much",
                labels='',
                labels_old=''),
            status=302)
        self.app.get('/wiki/%s/' % title)

    def test_project_feed(self):
        self.app.get('/feed.rss')
        self.app.get('/feed.atom')

    def test_wiki_feed(self):
        self.app.get('/wiki/feed.rss')
        self.app.get('/wiki/feed.atom')

    def test_wiki_page_feed(self):
        self.app.post('/wiki/Root/update', params={
                'title':'Root',
                'text':'',
                'labels':'',
                'labels_old':'',
                'viewable_by-0.id':'all'})
        self.app.get('/wiki/Root/feed.rss')
        self.app.get('/wiki/Root/feed.atom')

    def test_ticket_list_feed(self):
        self.app.get('/bugs/feed.rss')
        self.app.get('/bugs/feed.atom')

    def test_ticket_feed(self):
        self.app.get('/bugs/1/feed.rss')
        r = self.app.get('/bugs/1/feed.atom')
        assert 'created' in r
        self.app.post('/bugs/1/update_ticket', params=dict(
                assigned_to='',
                ticket_num='',
                labels='',
                labels_old='',
                summary='This is a new ticket',
                status='unread',
                milestone='',
                description='This is another description'))
        r = self.app.get('/bugs/1/feed.atom')
        assert '=&gt;' in r
        assert '\n+' in r

