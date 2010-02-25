from pylons import g, c
import os
import pyforge

from ming.orm.ormsession import ThreadLocalORMSession

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
        file_name = 'info.png'
        file_path = os.path.join(pyforge.__path__[0],'public','images',file_name)
        file_data = file(file_path).read()
        upload = ('icon', file_name, file_data)

        r = self.app.get('/mozilla/_admin/', extra_environ=dict(username='root'))
        r = self.app.post('/mozilla/_admin/update',
                          params=dict(name='Mozq1', css='', homepage='# MozQ1'),
                          extra_environ=dict(username='root'), upload_files=[upload])
        r = self.app.get('/mozilla/icon')
        assert r.body == file_data

    def test_invite(self):
        r = self.app.get('/mozilla/_moderate/', extra_environ=dict(username='root'))
        r = self.app.post('/mozilla/_moderate/invite',
                          params=dict(pid='Mozilla 1', invite='on'),
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
                          params=dict(pid='Mozilla 1'),
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
        r = self.app.get(r.location)
        assert 'error' in r

    def test_neighborhood_project(self):
        r = self.app.get('/mozilla/test/home/', status=302)
        r = self.app.get('/mozilla/Mozilla 1/home/', status=200)
        r = self.app.get('/projects/test/sub1/home/')
        r = self.app.get('/projects/test/sub1/', status=302)
        r = self.app.get('/projects/test/no_such_app/', status=404)


