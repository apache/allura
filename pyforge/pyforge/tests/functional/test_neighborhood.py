from pylons import g, c
import os
import pyforge

from ming.orm.ormsession import ThreadLocalORMSession
import Image, StringIO

from pyforge.tests import TestController

class TestNeighborhood(TestController):

    def test_admin(self):
        r = self.app.get('/adobe/_admin/', extra_environ=dict(username='root'))
        r = self.app.post('/adobe/_admin/update_acl',
                          params={'permission':'moderate',
                                  'new.add':'on',
                                  'new.username':'test_user'},
                          extra_environ=dict(username='root'))
        r = self.app.post('/adobe/_admin/update_acl',
                          params={'permission':'read',
                                  'new.username':'',
                                  'user-0.id':'',
                                  'user-0.delete':'on'},
                          extra_environ=dict(username='root'))
        r = self.app.post('/adobe/_admin/update',
                          params=dict(name='Mozq1', css='', homepage='# MozQ1!'),
                          extra_environ=dict(username='root'))
        r = self.app.post('/adobe/_admin/update',
                          params=dict(name='Mozq1', css='', homepage='# MozQ1!\n[Root]'),
                          extra_environ=dict(username='root'))

    def test_icon(self):
        file_name = 'ui-icons_454545_256x240.png'
        file_path = os.path.join(pyforge.__path__[0],'public','css','forge','images',file_name)
        file_data = file(file_path).read()
        upload = ('icon', file_name, file_data)

        r = self.app.get('/adobe/_admin/', extra_environ=dict(username='root'))
        r = self.app.post('/adobe/_admin/update',
                          params=dict(name='Mozq1', css='', homepage='# MozQ1'),
                          extra_environ=dict(username='root'), upload_files=[upload])
        r = self.app.get('/adobe/icon')
        image = Image.open(StringIO.StringIO(r.body))
        assert image.size == (48,48)

    def test_invite(self):
        r = self.app.get('/adobe/_moderate/', extra_environ=dict(username='root'))
        r = self.app.post('/adobe/_moderate/invite',
                          params=dict(pid='adobe_1', invite='on'),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'error' in r
        r = self.app.post('/adobe/_moderate/invite',
                          params=dict(pid='no_such_user', invite='on'),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'error' in r
        r = self.app.post('/adobe/_moderate/invite',
                          params=dict(pid='test', invite='on'),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'invited' in r
        assert 'warning' not in r
        r = self.app.post('/adobe/_moderate/invite',
                          params=dict(pid='test', invite='on'),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'warning' in r
        r = self.app.post('/adobe/_moderate/invite',
                          params=dict(pid='test', uninvite='on'),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'uninvited' in r
        assert 'warning' not in r
        r = self.app.post('/adobe/_moderate/invite',
                          params=dict(pid='test', uninvite='on'),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'warning' in r
        r = self.app.post('/adobe/_moderate/invite',
                          params=dict(pid='test', invite='on'),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'invited' in r
        assert 'warning' not in r

    def test_evict(self):
        r = self.app.get('/adobe/_moderate/', extra_environ=dict(username='root'))
        r = self.app.post('/adobe/_moderate/evict',
                          params=dict(pid='test'),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'error' in r
        r = self.app.post('/adobe/_moderate/evict',
                          params=dict(pid='adobe_1'),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'error' not in r

    def test_home(self):
        r = self.app.get('/adobe/')

    def test_register(self):
        r = self.app.post('/adobe/register',
                          params=dict(pid='mymoz'),
                          extra_environ=dict(username='*anonymous'),
                          status=401)
        r = self.app.post('/adobe/register',
                          params=dict(pid='mymoz'),
                          extra_environ=dict(username='root'))
        r = self.app.post('/adobe/register',
                          params=dict(pid='foo.mymoz'),
                          extra_environ=dict(username='root'))
        assert 'error' in r.cookies_set['webflash']

    def test_neighborhood_project(self):
        r = self.app.get('/adobe/test/home/', status=302)
        r = self.app.get('/adobe/adobe_1/home/', status=200)
        r = self.app.get('/p/test/sub1/home/')
        r = self.app.get('/p/test/sub1/', status=302)
        r = self.app.get('/p/test/no_such_app/', status=404)

    def test_neighborhood_awards(self):
        file_name = 'adobe_icon.png'
        file_path = os.path.join(pyforge.__path__[0],'public','images',file_name)
        file_data = file(file_path).read()
        upload = ('icon', file_name, file_data)

        r = self.app.get('/adobe/_admin/awards', extra_environ=dict(username='root'))
        r = self.app.post('/adobe/_admin/awards/create',
                          params=dict(short='FOO', full='A basic foo award'),
                          extra_environ=dict(username='root'), upload_files=[upload])
        r = self.app.get('/adobe/_admin/awards/FOO', extra_environ=dict(username='root'))
        r = self.app.get('/adobe/_admin/awards/FOO/icon', extra_environ=dict(username='root'))
        image = Image.open(StringIO.StringIO(r.body))
        assert image.size == (48,48)
        r = self.app.post('/adobe/_admin/awards/grant',
                          params=dict(grant='FOO', recipient='adobe_1'),
                          extra_environ=dict(username='root'))
        r = self.app.get('/adobe/_admin/awards/FOO/adobe_1', extra_environ=dict(username='root'))
        r = self.app.post('/adobe/_admin/awards/FOO/adobe_1/revoke',
                          extra_environ=dict(username='root'))
        r = self.app.post('/adobe/_admin/awards/FOO/delete',
                          extra_environ=dict(username='root'))

    def test_site_css(self):
        r = self.app.get('/p/site_style.css')
        assert(
"""a {color: #0088cc; text-decoration: none;}""" in r)
        assert(
""".ui-state-default.ui-button:active:hover, .ui-state-active.ui-button {
	text-decoration: none !important;
	color: #000000 !important;""" in r)
        assert(
"""#footer a:link, #footer a:visited, #footer a:hover, #footer a:active{
    color: #454545;
    text-decoration: none;
}""" in r)
        self.app.post('/p/_admin/update',
                          params=dict(name='Projects', css='', homepage='projects',
                          color1='#aaa', color2='#bbb', color3='#ccc', color4='#ddd'),
                          extra_environ=dict(username='root'))
        r = self.app.get('/p/site_style.css')
        assert(
"""a {color: #aaa; text-decoration: none;}""" in r)
        assert(
""".ui-state-default.ui-button:active:hover, .ui-state-active.ui-button {
	text-decoration: none !important;
	color: #bbb !important;""" in r)
        assert(
"""#footer a:link, #footer a:visited, #footer a:hover, #footer a:active{
    color: #ccc;
    text-decoration: none;
}""" in r)

    def test_custom_css(self):
        r = self.app.get('/adobe/site_style.css')
        assert("body {background-color: #f00;}" not in r)
        r = self.app.post('/adobe/_admin/update',
                          params=dict(name='Adobe', css='body {background-color: #f00;}', homepage=''),
                          extra_environ=dict(username='root'))
        r = self.app.get('/adobe/site_style.css')
        assert("body {background-color: #f00;}" in r)


