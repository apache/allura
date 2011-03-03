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
        self.app.post('/admin/update_homepage', {'description': 'A long description ?'})
        self.app.post('/admin/update', params=dict(
                name='Test Project',
                shortname='test',
                short_description=u'\u00bf A Test Project ?'.encode('utf-8'),
                labels='aaa,bbb'))
        r = self.app.get('/admin/overview')
        assert 'A Test Project ?' in r
        assert 'Test Subproject' not in r

        r = self.app.get('/home/')
        assert 'A long description ?' in r

        # Add a subproject
        self.app.post('/admin/update_mounts', params={
                'new.install':'install',
                'new.ep_name':'',
                'new.ordinal':1,
                'new.mount_point':'test-subproject',
                'new.mount_label':'Test Subproject'})
        r = self.app.get('/admin/overview')
        assert 'Test Subproject' in r
        # Rename a subproject
        self.app.post('/admin/update_mounts', params={
                'subproject-0.shortname':'test/test-subproject',
                'subproject-0.name':'Tst Sbprj',
                'subproject-0.ordinal':100,
                })
        r = self.app.get('/admin/overview')
        assert 'Tst Sbprj' in r
        # Remove a subproject
        self.app.post('/admin/update_mounts', params={
                'subproject-0.delete':'on',
                'subproject-0.shortname':'test/test-subproject',
                'new.ep_name':'',
                })

        # Add a tool
        r = self.app.post('/admin/update_mounts', params={
                'new.install':'install',
                'new.ep_name':'Wiki',
                'new.ordinal':1,
                'new.mount_point':'test-tool',
                'new.mount_label':'Test Tool'})
        assert 'error' not in self.webflash(r)
        # check tool in the nav
        r = self.app.get('/p/test/test-tool/').follow()
        active_link = r.html.findAll('span',{'class':'diamond'})
        assert len(active_link) == 1
        assert active_link[0].parent['href'] == '/p/test/test-tool/'
        r = self.app.post('/admin/update_mounts', params={
                'new.install':'install',
                'new.ep_name':'Wiki',
                'new.ordinal':1,
                'new.mount_point':'test-tool2',
                'new.mount_label':'Test Tool2'})
        assert 'error' not in self.webflash(r)
        # check the nav - the similarly named tool should NOT be active
        r = self.app.get('/p/test/test-tool/Home/')
        active_link = r.html.findAll('span',{'class':'diamond'})
        assert len(active_link) == 1
        assert active_link[0].parent['href'] == '/p/test/test-tool/'
        r = self.app.get('/p/test/test-tool2/Home/')
        active_link = r.html.findAll('span',{'class':'diamond'})
        assert len(active_link) == 1
        assert active_link[0].parent['href'] == '/p/test/test-tool2/'
        # check can't create dup tool
        r = self.app.post('/admin/update_mounts', params={
                'new.install':'install',
                'new.ep_name':'Wiki',
                'new.ordinal':1,
                'new.mount_point':'test-tool',
                'new.mount_label':'Test Tool'})
        assert 'error' in self.webflash(r)
        # Rename a tool
        self.app.post('/admin/update_mounts', params={
                'tool-0.mount_point':'test-tool',
                'tool-0.mount_label':'Tst Tuul',
                'tool-0.ordinal':200,
                })
        r = self.app.get('/admin/overview')
        assert 'Tst Tuul' in r
        # Remove a tool
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
                short_description='A Test Project'),
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
                short_description='A Test Project'),
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
                delete='on'))
        r = self.app.get('/p/test/admin/overview')
        assert 'This project has been deleted and is not visible to non-admin users' in r
        assert not r.html.find('input',{'value':'Delete Project'})
        assert r.html.find('input',{'value':'Undelete Project'})
        self.app.post('/admin/update', params=dict(
                name='Test Project',
                shortname='test',
                short_description='A Test Project',
                undelete='on'))
        r = self.app.get('/p/test/admin/overview')
        assert 'This project has been deleted and is not visible to non-admin users' not in r
        assert r.html.find('input',{'value':'Delete Project'})
        assert not r.html.find('input',{'value':'Undelete Project'})

    def test_project_homepage(self):
        r = self.app.get('/admin/homepage')
        assert 'Awesome description' not in r
        self.app.post('/admin/update_homepage', {'description': 'Awesome description'})
        r = self.app.get('/admin/homepage')
        assert 'Awesome description' in r
        r = self.app.get('/p/test/home/')
        assert 'Awesome description' in r, r

    def test_project_permissions(self):
        r = self.app.get('/admin/permissions/')
        assert len(r.html.findAll('input', {'name': 'card-0.value'})) == 1
        select = r.html.find('select', {'name': 'card-0.new'})
        opt_admin = select.find(text='Admin').parent
        opt_developer = select.find(text='Developer').parent
        assert opt_admin.name == 'option'
        assert opt_developer.name == 'option'
        r = self.app.post('/admin/permissions/update', params={
                'card-0.new': opt_developer['value'],
                'card-0.value': opt_admin['value'],
                'card-0.id': 'create'})
        r = self.app.get('/admin/permissions/')
        assigned_ids = [t['value'] for t in r.html.findAll('input', {'name': 'card-0.value'})]
        assert len(assigned_ids) == 2
        assert opt_developer['value'] in assigned_ids
        assert opt_admin['value'] in assigned_ids

    def test_project_groups(self):
        r = self.app.get('/admin/groups/')
        developer_id = r.html.find('input', {'name': 'card-1.id'})['value']
        r = self.app.post('/admin/groups/update', params={
                'card-1.id': developer_id,
                'card-1.new': 'test-user'})
        r = self.app.get('/admin/groups/')
        users = [t.previous.strip() for t in r.html.findAll('input', {'name': 'card-1.value'})]
        assert 'test-user' in users
        # Make sure we can open role page for builtin role
        r = self.app.get('/admin/groups/' + developer_id + '/', validate_chunk=True)

    def test_project_multi_groups(self):
        r = self.app.get('/admin/groups/')
        user_id = M.User.by_username('test-admin')._id
        admin_id = r.html.find('input', {'name': 'card-0.id'})['value']
        for x in range(2):
            form = r.forms[0]
            form['card-0.new'].value = 'test-user'
            r = form.submit().follow()
        r = self.app.get('/admin/groups/')
        assert 'test-user' in str(r), r.showbrowser()
        r = self.app.post('/admin/groups/update', params={
                'card-0.id':admin_id,
                'card-0.value':str(user_id)})
        r = self.app.get('/admin/groups/')
        assert 'test-user' not in str(r), r.showbrowser()


    def test_new_group(self):
        r = self.app.get('/admin/groups/new', validate_chunk=True)
        r = self.app.post('/admin/groups/create', params={'name': 'Developer'})
        assert 'error' in self.webflash(r)
        r = self.app.post('/admin/groups/create', params={'name': 'RoleNew1'})
        r = self.app.get('/admin/groups/')
        assert 'RoleNew1' in r
        role_id = r.html.find(text='RoleNew1').findPrevious('input', {'type': 'hidden'})['value']
        r = self.app.get('/admin/groups/' + role_id + '/', validate_chunk=True)

        r = self.app.post('/admin/groups/' + str(role_id) + '/update', params={'_id': role_id, 'name': 'Developer'})
        assert 'error' in self.webflash(r)
        assert 'already exists' in self.webflash(r)

        r = self.app.post('/admin/groups/' + str(role_id) + '/update', params={'_id': role_id, 'name': 'rleNew2'}).follow()
        assert 'RoleNew1' not in r
        assert 'rleNew2' in r

        r = self.app.post('/admin/groups/' + str(role_id) + '/update', params={'_id': role_id, 'name': 'rleNew2', 'delete': 'delete'})
        assert 'deleted' in self.webflash(r)
        r = self.app.get('/admin/groups/')
        roles = [t.string for t in r.html.findAll('h3')]
        assert 'RoleNew1' not in roles
        assert 'rleNew2' not in roles
