from pylons import g
from formencode.variabledecode import variable_encode

from pyforge.tests import TestController
from pyforge import model as M

class TestDiscuss(TestController):

    def test_subscribe_unsubscribe(self):
        home = self.app.get('/wiki/_discuss/')
        subscribed = [ i for i in home.html.findAll('input')
                       if i.get('type') == 'checkbox'][0]
        assert not subscribed.get('checked')
        link = [ a for a in home.html.findAll('a')
                 if 'thread' in a['href'] ][0]
        params = {
            'threads-0._id':link['href'][len('/p/test/wiki/_discuss/thread/'):-1],
            'threads-0.subscription':'on' }
        r = self.app.post('/wiki/_discuss/subscribe',
                          params=params,
                          headers={'Referer':'/wiki/_discuss/'})
        r = r.follow()
        subscribed = [ i for i in r.html.findAll('input')
                       if i.get('type') == 'checkbox'][0]
        assert subscribed.get('checked')
        params = {
            'threads-0._id':link['href'][len('/p/test/wiki/_discuss/thread/'):-1]
            }
        r = self.app.post('/wiki/_discuss/subscribe',
                          params=params,
                          headers={'Referer':'/wiki/_discuss/'})
        r = r.follow()
        subscribed = [ i for i in r.html.findAll('input')
                       if i.get('type') == 'checkbox'][0]
        assert not subscribed.get('checked')

    def _make_post(self, text):
        home = self.app.get('/wiki/_discuss/')
        thread_link = [ a for a in home.html.findAll('a')
                 if 'thread' in a['href'] ][0]['href']
        thread = self.app.get(thread_link)
        for f in thread.html.findAll('form'):
            if f['action'].endswith('/post'):
                break
        params = dict(text=text)
        r = self.app.post(f['action'].encode('utf-8'), params=params,
                          headers={'Referer':thread_link.encode("utf-8")})
        r = r.follow()
        return r

    def test_post(self):
        home = self.app.get('/wiki/_discuss/')
        thread_link = [ a for a in home.html.findAll('a')
                 if 'thread' in a['href'] ][0]['href']
        r = self._make_post('This is a post')
        assert 'This is a post' in r, r
        for link in r.html.findAll('a'):
            if 'ermalink' in str(link):
                break
        post_link = str(link['href'])
        r = self.app.get(post_link)
        r = self.app.get(post_link[:-2], status=302)
        r = self.app.post(post_link,
                          params=dict(text='This is a new post'),
                          headers={'Referer':thread_link.encode("utf-8")})
        r = r.follow()
        assert 'This is a new post' in r, r
        r = self.app.get(post_link)
        assert str(r).count('This is a new post') == 2
        r = self.app.post(post_link + 'reply',
                          params=dict(text='Tis a reply'),
                          headers={'Referer':post_link.encode("utf-8")})
        r = self.app.get(thread_link)
        assert 'Tis a reply' in r, r
        permalinks = [ link['href'].encode('utf-8') for link in r.html.findAll('a')
                       if 'Permalink' in str(link) ]
        self.app.post(permalinks[1]+'flag')
        self.app.post(permalinks[1]+'moderate', params=dict(delete='delete'))
        self.app.post(permalinks[0]+'moderate', params=dict(spam='spam'))

class TestAttachment(TestController):

    def setUp(self):
        super(TestAttachment, self).setUp()
        home = self.app.get('/wiki/_discuss/')
        self.thread_link = [ a['href'].encode("utf-8")
                             for a in home.html.findAll('a')
                             if 'thread' in a['href'] ][0]
        thread = self.app.get(self.thread_link)
        for f in thread.html.findAll('form'):
            if f['action'].endswith('/post'):
                break
        self.post_form_link = f['action'].encode('utf-8')
        r = self.app.post(f['action'].encode('utf-8'), params=dict(text='Test Post'),
                          headers={'Referer':self.thread_link})
        r = r.follow()
        for link in r.html.findAll('a'):
            if 'ermalink' in str(link):
                break
        self.post_link = str(link['href'])

    def test_attach(self):
        r = self.app.post(self.post_link + 'attach',
                          upload_files=[('file_info', 'test.txt', 'HiThere!')])
        r = self.app.get(self.post_link)
        for alink in r.html.findAll('a'):
            if 'attachment' in alink['href']:
                alink = str(alink['href'])
                break
        r = self.app.get(alink)
        assert 'Content-Disposition' in r.headers
        assert r.headers['Content-Disposition'] == 'attachment;filename=test.txt'
        r = self.app.post(self.post_link + 'attach',
                          upload_files=[('file_info', 'test.o12', 'HiThere!')])
        r = self.app.post(alink, params=dict(delete='on'))
