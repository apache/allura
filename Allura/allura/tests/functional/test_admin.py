import os, allura
import Image, StringIO

from nose.tools import assert_equals, assert_true
from pylons import g, c

from ming.orm.ormsession import ThreadLocalORMSession

try:
    import sfx
except ImportError:
    sfx = None

from allura.tests import TestController
from allura import model as M
from allura.lib import helpers as h


class TestProjectAdmin(TestController):

    def test_admin_controller(self):
        self.app.get('/admin/')
        self.app.post('/admin/update', params=dict(
                name='Test Project',
                shortname='test',
                short_description=u'\u00bf A Test Project ?'.encode('utf-8'),
                description=u'\u00bf A long description ?'.encode('utf-8'),
                labels='aaa,bbb'))
        r = self.app.get('/admin/overview')
        # Add/Remove a subproject
        self.app.post('/admin/update_mounts', params={
                'new.install':'install',
                'new.ep_name':'',
                'new.ordinal':1,
                'new.mount_point':'test-subproject',
                'new.mount_label':'Test Subproject'})
        self.app.post('/admin/update_mounts', params={
                'subproject-0.delete':'on',
                'subproject-0.shortname':'test/test-subproject',
                'new.ep_name':'',
                })
        # Add/Remove a tool
        r = self.app.post('/admin/update_mounts', params={
                'new.install':'install',
                'new.ep_name':'Wiki',
                'new.ordinal':1,
                'new.mount_point':'test-tool',
                'new.mount_label':'Test Tool'})
        assert 'error' not in r.cookies_set.get('webflash', ''), r.showbrowser()
        # check the nav
        r = self.app.get('/p/test/test-tool/').follow()
        active_link = r.html.findAll('span',{'class':'arrow'})
        assert len(active_link) == 1
        assert active_link[0].parent['href'] == '/p/test/test-tool/'
        r = self.app.post('/admin/update_mounts', params={
                'new.install':'install',
                'new.ep_name':'Wiki',
                'new.ordinal':1,
                'new.mount_point':'test-tool2',
                'new.mount_label':'Test Tool2'})
        assert 'error' not in r.cookies_set.get('webflash', ''), r.showbrowser()
        # check the nav - the similarly named tool should NOT be active
        r = self.app.get('/p/test/test-tool/Home/')
        active_link = r.html.findAll('span',{'class':'arrow'})
        assert len(active_link) == 1
        assert active_link[0].parent['href'] == '/p/test/test-tool/'
        r = self.app.get('/p/test/test-tool2/Home/')
        active_link = r.html.findAll('span',{'class':'arrow'})
        assert len(active_link) == 1
        assert active_link[0].parent['href'] == '/p/test/test-tool2/'
        r = self.app.post('/admin/update_mounts', params={
                'new.install':'install',
                'new.ep_name':'Wiki',
                'new.ordinal':1,
                'new.mount_point':'test-tool',
                'new.mount_label':'Test Tool'})
        assert 'error' in r.cookies_set.get('webflash', ''), r.showbrowser()
        self.app.post('/admin/update_mounts', params={
                'tool-0.delete':'on',
                'tool-0.mount_point':'test-tool',
                'new.ep_name':'',
                })
        # Update ACL
        h.set_context('test', 'wiki')
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
                'new.username':'test-user'})
        self.app.post('/admin/update_acl', params={
                'permission':'tool',
                'new.add':'on',
                'new.id':'',
                'new.username':'no_such_user'})
        # Update project roles
        self.app.post('/admin/update_roles', params={
                'new.add':'on',
                'new.name':'test_role'})
        role1 = M.ProjectRole.by_name('test_role')
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

    def test_tool_list(self):
        r = self.app.get('/admin/tools')
        new_ep_opts = r.html.findAll('a',{'class':"install_trig"})
        strings = [ ' '.join(opt.find('span').string.strip().split()) for opt in new_ep_opts ]
        expected_tools = [
            'External Link',
            'Git',
            'Mercurial',
            'SVN',
            'Wiki',
            'Tickets',
            'Discussion',
            'Downloads' ]
        if sfx:
            expected_tools += [
            'Mailing List (alpha)',
            'VHOST (alpha)',
            'MySQL Databases (alpha)',
            'Project Web Outgoing Email (alpha)',
            'Classic Hosted Apps (alpha)' ]
        expected_tools += [
            'Chat (alpha)',
            'Blog (alpha)',
            'Subproject']
        assert strings == expected_tools

    def test_project_icon(self):
        file_name = 'neo-icon-set-454545-256x350.png'
        file_path = os.path.join(allura.__path__[0],'public','nf','allura','images',file_name)
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
        file_name = 'neo-icon-set-454545-256x350.png'
        file_path = os.path.join(allura.__path__[0],'public','nf','allura','images',file_name)
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
