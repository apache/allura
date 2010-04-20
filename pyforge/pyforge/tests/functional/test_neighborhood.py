from pylons import g, c
import os
import pyforge

from ming.orm.ormsession import ThreadLocalORMSession
import Image, StringIO

from pyforge.tests import TestController

class TestNeighborhood(TestController):

    def test_admin(self):
        r = self.app.get('/mozilla/_admin/', extra_environ=dict(username='root'))
        r = self.app.post('/mozilla/_admin/update_acl',
                          params={'permission':'moderate',
                                  'new.add':'on',
                                  'new.username':'test_user'},
                          extra_environ=dict(username='root'))
        r = self.app.post('/mozilla/_admin/update_acl',
                          params={'permission':'read',
                                  'new.username':'',
                                  'user-0.id':'',
                                  'user-0.delete':'on'},
                          extra_environ=dict(username='root'))
        r = self.app.post('/mozilla/_admin/update',
                          params=dict(name='Mozq1', css='', homepage='# MozQ1!'),
                          extra_environ=dict(username='root'))
        r = self.app.post('/mozilla/_admin/update',
                          params=dict(name='Mozq1', css='', homepage='# MozQ1!\n[Root]'),
                          extra_environ=dict(username='root'))

    def test_icon(self):
        file_name = 'adobe_header.png'
        file_path = os.path.join(pyforge.__path__[0],'public','images',file_name)
        file_data = file(file_path).read()
        upload = ('icon', file_name, file_data)

        r = self.app.get('/mozilla/_admin/', extra_environ=dict(username='root'))
        r = self.app.post('/mozilla/_admin/update',
                          params=dict(name='Mozq1', css='', homepage='# MozQ1'),
                          extra_environ=dict(username='root'), upload_files=[upload])
        r = self.app.get('/mozilla/icon')
        image = Image.open(StringIO.StringIO(r.body))
        assert image.size == (48,48)

    def test_invite(self):
        r = self.app.get('/mozilla/_moderate/', extra_environ=dict(username='root'))
        r = self.app.post('/mozilla/_moderate/invite',
                          params=dict(pid='mozilla_1', invite='on'),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'error' in r
        r = self.app.post('/mozilla/_moderate/invite',
                          params=dict(pid='no_such_user', invite='on'),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'error' in r
        r = self.app.post('/mozilla/_moderate/invite',
                          params=dict(pid='test', invite='on'),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'invited' in r
        assert 'warning' not in r
        r = self.app.post('/mozilla/_moderate/invite',
                          params=dict(pid='test', invite='on'),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'warning' in r
        r = self.app.post('/mozilla/_moderate/invite',
                          params=dict(pid='test', uninvite='on'),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'uninvited' in r
        assert 'warning' not in r
        r = self.app.post('/mozilla/_moderate/invite',
                          params=dict(pid='test', uninvite='on'),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'warning' in r
        r = self.app.post('/mozilla/_moderate/invite',
                          params=dict(pid='test', invite='on'),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'invited' in r
        assert 'warning' not in r

    def test_evict(self):
        r = self.app.get('/mozilla/_moderate/', extra_environ=dict(username='root'))
        r = self.app.post('/mozilla/_moderate/evict',
                          params=dict(pid='test'),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'error' in r
        r = self.app.post('/mozilla/_moderate/evict',
                          params=dict(pid='mozilla_1'),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'error' not in r

    def test_home(self):
        r = self.app.get('/mozilla/')

    def test_register(self):
        r = self.app.post('/mozilla/register',
                          params=dict(pid='mymoz'),
                          extra_environ=dict(username='*anonymous'),
                          status=401)
        r = self.app.post('/mozilla/register',
                          params=dict(pid='mymoz'),
                          extra_environ=dict(username='root'))
        r = self.app.post('/mozilla/register',
                          params=dict(pid='foo.mymoz'),
                          extra_environ=dict(username='root'))
        assert 'error' in r.cookies_set['webflash']

    def test_neighborhood_project(self):
        r = self.app.get('/mozilla/test/home/', status=302)
        r = self.app.get('/mozilla/mozilla_1/home/', status=200)
        r = self.app.get('/p/test/sub1/home/')
        r = self.app.get('/p/test/sub1/', status=302)
        r = self.app.get('/p/test/no_such_app/', status=404)

    def test_site_css(self):
        r = self.app.get('/p/site_style.css')
        assert(
"""a{
    color: #104a75;
    text-decoration: none;
}""" in r)
        assert(
"""#nav_menu_missing{
    height: 0;
    padding-top: 5px;
    border: 5px solid #aed0ea;
    border-width: 0 0 5px 0;
}""" in r)
        assert(
"""#content{
    border-style: solid;
    border-color: #D7E8F5 #aed0ea #D7E8F5 #D7E8F5;
    border-right-color: #aed0ea;
    border-width: 5px 1px 0 5px;
    width: 789px;
    min-height: 400px;
}""" in r)
        self.app.post('/p/_admin/update',
                          params=dict(name='Projects', css='', homepage='projects',
                          color1='#aaa', color2='#bbb', color3='#ccc', color4='#ddd'),
                          extra_environ=dict(username='root'))
        r = self.app.get('/p/site_style.css')
        assert(
"""a{
    color: #aaa;
    text-decoration: none;
}
a:visited, a:hover {color: #aaa;}
a:hover {text-decoration: underline;}""" in r)
        assert(
"""#nav_menu_missing{
    height: 0;
    padding-top: 5px;
    border: 5px solid #bbb;
    border-width: 0 0 5px 0;
}""" in r)
        assert(
"""#content{
    border-style: solid;
    border-color: #ddd #bbb #ddd #ddd;
    border-right-color: #bbb;
    border-width: 5px 1px 0 5px;
    width: 789px;
    min-height: 400px;
}""" in r)


