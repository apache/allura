import os, pyforge
import Image, StringIO

from pylons import g, c

from ming.orm.ormsession import ThreadLocalORMSession

from pyforge.tests import TestController
from pyforge import model as M
from pyforge.lib import helpers as h

class TestProjectAdmin(TestController):

    def test_admin_controller(self):
        self.app.get('/admin/')
        self.app.post('/admin/update', params=dict(
                name='Test Project',
                shortname='test',
                short_description='A Test Project',
                description='A long description',
                labels='aaa,bbb'))
        # Add/Remove a subproject
        self.app.post('/admin/update_mounts', params={
                'new.install':'install',
                'new.ep_name':'',
                'new.mount_point':'test_subproject'})
        self.app.post('/admin/update_mounts', params={
                'subproject-0.delete':'on',
                'subproject-0.shortname':'test/test_subproject',
                'new.ep_name':'',
                })
        # Add/Remove a tool
        self.app.post('/admin/update_mounts', params={
                'new.install':'install',
                'new.ep_name':'hello_forge',
                'new.mount_point':'test_tool'})
        self.app.post('/admin/update_mounts', params={
                'tool-0.delete':'on',
                'tool-0.mount_point':'test_tool',
                'new.ep_name':'',
                })
        # Update ACL
        h.set_context('test', 'hello')
        role = M.User.anonymous().project_role()
        self.app.post('/admin/update_acl', params={
                'permission':'tool',
                'new.add':'on',
                'new.id':str(role._id)})
        self.app.post('/admin/update_acl', params={
                'new.id':'',
                'permission':'tool',
                'role-0.delete':'on',
                'role-0.id':str(role._id)})
        self.app.post('/admin/update_acl', params={
                'permission':'tool',
                'new.add':'on',
                'new.id':'',
                'new.username':'test_user'})
        self.app.post('/admin/update_acl', params={
                'permission':'tool',
                'new.add':'on',
                'new.id':'',
                'new.username':'no_such_user'})
        # Update project roles
        self.app.post('/admin/update_roles', params={
                'new.add':'on',
                'new.name':'test_role'})
        role1 = M.ProjectRole.query.find(dict(name='test_role')).one()
        self.app.post('/admin/update_roles', params={
                'role-0.id':str(role1._id),
                'role-0.new.add':'on',
                'role-0.new.id':str(role._id),
                'new.name':''})
        self.app.post('/admin/update_roles', params={
                'role-0.id':str(role1._id),
                'role-0.new.id':'',
                'role-0.subroles-0.delete':'on',
                'role-0.subroles-0.id':str(role._id),
                'new.name':''})
        self.app.post('/admin/update_roles', params={
                'role-0.id':str(role1._id),
                'role-0.new.id':'',
                'role-0.delete':'on',
                'new.name':''})
        # Create a role when there are no existing roles
        self.app.post('/admin/update_roles', params={
                'new.add':'on',
                'new.name':'test_role',
                'role-0.id':str(role1._id)})

    def test_project_icon(self):
        file_name = 'ui-icons_454545_256x240.png'
        file_path = os.path.join(pyforge.__path__[0],'public','css','forge','images',file_name)
        file_data = file(file_path).read()
        upload = ('icon', file_name, file_data)

        self.app.get('/admin/')
        self.app.post('/admin/update', params=dict(
                name='Test Project',
                shortname='test',
                short_description='A Test Project',
                description='A long description'),
                upload_files=[upload])
        r = self.app.get('/p/test/icon')
        image = Image.open(StringIO.StringIO(r.body))
        assert image.size == (48,48)

    def test_project_screenshot(self):
        file_name = 'ui-icons_454545_256x240.png'
        file_path = os.path.join(pyforge.__path__[0],'public','css','forge','images',file_name)
        file_data = file(file_path).read()
        upload = ('screenshot', file_name, file_data)

        self.app.get('/admin/')
        self.app.post('/admin/update', params=dict(
                name='Test Project',
                shortname='test',
                short_description='A Test Project',
                description='A long description'),
                upload_files=[upload])
        project = M.Project.query.find({'shortname':'test'}).first()
        filename = project.get_screenshots()[0].filename
        r = self.app.get('/p/test/screenshot/'+filename)
        uploaded = Image.open(file_path)
        screenshot = Image.open(StringIO.StringIO(r.body))
        assert uploaded.size == screenshot.size
        r = self.app.get('/p/test/screenshot/'+filename+'/thumb')
        thumb = Image.open(StringIO.StringIO(r.body))
        assert thumb.size == (150,150)

    def test_project_delete_undelete(self):
        r = self.app.get('/p/test/admin/overview')
        assert 'This project has been deleted and is not visible to non-admin users' not in r
        assert r.html.find('input',{'value':'Delete Project'})
        assert not r.html.find('input',{'value':'Undelete Project'})
        self.app.post('/admin/update', params=dict(
                name='Test Project',
                shortname='test',
                short_description='A Test Project',
                description='A long description',
                delete='on'))
        r = self.app.get('/p/test/admin/overview')
        assert 'This project has been deleted and is not visible to non-admin users' in r
        assert not r.html.find('input',{'value':'Delete Project'})
        assert r.html.find('input',{'value':'Undelete Project'})
        self.app.post('/admin/update', params=dict(
                name='Test Project',
                shortname='test',
                short_description='A Test Project',
                description='A long description',
                undelete='on'))
        r = self.app.get('/p/test/admin/overview')
        assert 'This project has been deleted and is not visible to non-admin users' not in r
        assert r.html.find('input',{'value':'Delete Project'})
        assert not r.html.find('input',{'value':'Undelete Project'})
