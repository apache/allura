from pylons import g, c
import os
import allura

from ming.orm.ormsession import ThreadLocalORMSession
import Image, StringIO

from allura.tests import TestController

class TestNeighborhood(TestController):

    def test_home_project(self):
        r = self.app.get('/adobe/home/')
        assert r.location.endswith('/adobe/home/Home/')
        r = r.follow()
        assert 'Welcome' in str(r), str(r)
        r = self.app.get('/adobe/admin/')
        assert r.location.endswith('/adobe/admin/overview')
        r = r.follow()
        assert 'admin' in str(r), str(r)

    def test_redirect(self):
        r = self.app.post('/adobe/_admin/update',
                          params=dict(redirect='home/Home/'),
                          extra_environ=dict(username='root'))
        r = self.app.get('/adobe/')
        assert r.location.endswith('/adobe/home/Home/')

    def test_admin(self):
        r = self.app.get('/adobe/_admin/', extra_environ=dict(username='root'))
        r = self.app.post('/adobe/_admin/update_acl',
                          params={'permission':'moderate',
                                  'new.add':'on',
                                  'new.username':'test-user'},
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
        file_name = 'neo-icon-set-454545-256x350.png'
        file_path = os.path.join(allura.__path__[0],'public','nf','allura','images',file_name)
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
                          params=dict(pid='adobe-1', invite='on'),
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
                          params=dict(pid='adobe-1'),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'error' not in r

    def test_home(self):
        r = self.app.get('/adobe/')

    def test_register(self):
        r = self.app.post('/adobe/register',
                          params=dict(project_unixname='mymoz', project_name='', project_description=''),
                          extra_environ=dict(username='*anonymous'),
                          status=302)
        r = self.app.post('/adobe/register',
                          params=dict(project_unixname='foo.mymoz', project_name='', project_description=''),
                          extra_environ=dict(username='root'))
        assert r.html.find('div',{'class':'error'}).string == 'Please use only letters, numbers, and dash characters.'
        r = self.app.post('/p/register',
                          params=dict(project_unixname='test', project_name='', project_description=''),
                          extra_environ=dict(username='root'))
        assert 'error' in r.cookies_set['webflash']
        r = self.app.post('/adobe/register',
                          params=dict(project_unixname='mymoz', project_name='', project_description=''),
                          extra_environ=dict(username='root'))

    def test_neighborhood_project(self):
        r = self.app.get('/adobe/test/home/', status=302)
        r = self.app.get('/adobe/adobe-1/home/', status=200)
        r = self.app.get('/p/test/sub1/home/')
        r = self.app.get('/p/test/sub1/', status=302)
        r = self.app.get('/p/test/no-such-app/', status=404)

    def test_neighborhood_awards(self):
        file_name = 'adobe_icon.png'
        file_path = os.path.join(allura.__path__[0],'public','nf','images',file_name)
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
                          params=dict(grant='FOO', recipient='adobe-1'),
                          extra_environ=dict(username='root'))
        r = self.app.get('/adobe/_admin/awards/FOO/adobe-1', extra_environ=dict(username='root'))
        r = self.app.post('/adobe/_admin/awards/FOO/adobe-1/revoke',
                          extra_environ=dict(username='root'))
        r = self.app.post('/adobe/_admin/awards/FOO/delete',
                          extra_environ=dict(username='root'))

    def test_add_a_project_link(self):
        r = self.app.get('/p/')
        assert 'Add a Project' in r
        r = self.app.get('/u/')
        assert 'Add a Project' not in r
        r = self.app.get('/adobe/')
        assert 'Add a Project' not in r