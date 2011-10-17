import os, allura
import pkg_resources
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
                labels='aaa,bbb'))
        r = self.app.get('/admin/overview')
        assert 'A Test Project ?' in r
        assert 'Test Subproject' not in r

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

    def test_tool_permissions(self):
        self.app.get('/admin/')
        for i, ep in enumerate(pkg_resources.iter_entry_points('allura')):
            app = ep.load()
            if not app.installable: continue
            tool = ep.name
            self.app.post('/admin/update_mounts', params={
                    'new.install':'install',
                    'new.ep_name':tool,
                    'new.ordinal':i,
                    'new.mount_point':'test-%d' % i,
                    'new.mount_label':tool })
            r = self.app.get('/admin/test-%d/permissions' % i)
            cards = [
                tag for tag in r.html.findAll('input')
                if (
                    tag.get('type') == 'hidden' and
                    tag['name'].startswith('card-') and
                    tag['name'].endswith('.id')) ]
            assert len(cards) == len(app.permissions), cards

    def test_tool_list(self):
        r = self.app.get('/admin/tools')
        new_ep_opts = r.html.findAll('a',{'class':"install_trig"})
        tool_strings = [ ' '.join(opt.find('span').string.strip().split()) for opt in new_ep_opts ]
        expected_tools = [
            'External Link',
            'Git',
            'Mercurial',
            'SVN',
            'Wiki',
            'Tickets',
            'Discussion',
            'Chat (alpha)',
            'Blog',
            'Subproject']
        # check using sets, because their may be more tools installed by default
        # that we don't know about
        assert len(set(expected_tools) - set(tool_strings)) == 0, tool_strings

    def test_project_icon(self):
        file_name = 'neo-icon-set-454545-256x350.png'
        file_path = os.path.join(allura.__path__[0],'nf','allura','images',file_name)
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
        file_path = os.path.join(allura.__path__[0],'nf','allura','images',file_name)
        file_data = file(file_path).read()
        upload = ('screenshot', file_name, file_data)

        self.app.get('/admin/')
        self.app.post('/admin/add_screenshot', params=dict(
                caption='test me'),
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
        #FIX: home pages don't currently support screenshots (now that they're a wiki);
        # reinstate this code (or appropriate) when we have a macro for that
        #r = self.app.get('/p/test/home/')
        #assert '/p/test/screenshot/'+filename in r
        #assert 'test me' in r
        # test edit
        req = self.app.get('/admin/screenshots')
        req.forms[0]['caption'].value = 'aaa'
        req.forms[0].submit()
        #r = self.app.get('/p/test/home/')
        #assert 'aaa' in r
        # test delete
        req = self.app.get('/admin/screenshots')
        req.forms[1].submit()
        #r = self.app.get('/p/test/home/')
        #assert 'aaa' not in r

    def test_project_delete_undelete(self):
        # create a subproject
        self.app.post('/admin/update_mounts', params={
                'new.install':'install',
                'new.ep_name':'',
                'new.ordinal':1,
                'new.mount_point':'sub1',
                'new.mount_label':'sub1'})
        r = self.app.get('/p/test/admin/overview')
        assert 'This project has been deleted and is not visible to non-admin users' not in r
        assert r.html.find('input',{'name':'removal','value':''}).has_key('checked')
        assert not r.html.find('input',{'name':'removal','value':'deleted'}).has_key('checked')
        self.app.post('/admin/update', params=dict(
                name='Test Project',
                shortname='test',
                removal='deleted',
                short_description='A Test Project',
                delete='on'))
        r = self.app.get('/p/test/admin/overview')
        assert 'This project has been deleted and is not visible to non-admin users' in r
        assert not r.html.find('input',{'name':'removal','value':''}).has_key('checked')
        assert r.html.find('input',{'name':'removal','value':'deleted'}).has_key('checked')
        # make sure subprojects get deleted too
        r = self.app.get('/p/test/sub1/admin/overview')
        assert 'This project has been deleted and is not visible to non-admin users' in r
        self.app.post('/admin/update', params=dict(
                name='Test Project',
                shortname='test',
                removal='',
                short_description='A Test Project',
                undelete='on'))
        r = self.app.get('/p/test/admin/overview')
        assert 'This project has been deleted and is not visible to non-admin users' not in r
        assert r.html.find('input',{'name':'removal','value':''}).has_key('checked')
        assert not r.html.find('input',{'name':'removal','value':'deleted'}).has_key('checked')

    def test_project_delete_not_allowed(self):
        # turn off project delete option
        from allura.ext.admin.admin_main import config
        config['allow_project_delete'] = False
        # create a subproject
        self.app.post('/admin/update_mounts', params={
                'new.install':'install',
                'new.ep_name':'',
                'new.ordinal':1,
                'new.mount_point':'sub1',
                'new.mount_label':'sub1'})
        # root project doesn't have delete option
        r = self.app.get('/p/test/admin/overview')
        assert not r.html.find('input',{'name':'removal','value':'deleted'})
        # subprojects can still be deleted
        r = self.app.get('/p/test/sub1/admin/overview')
        assert r.html.find('input',{'name':'removal','value':'deleted'})
        # attempt to delete root project won't do anything
        self.app.post('/admin/update', params=dict(
                name='Test Project',
                shortname='test',
                removal='deleted',
                short_description='A Test Project',
                delete='on'))
        r = self.app.get('/p/test/admin/overview')
        assert 'This project has been deleted and is not visible to non-admin users' not in r
        # make sure subproject delete works
        self.app.post('/p/test/sub1/admin/update', params=dict(
                name='sub1',
                shortname='sub1',
                removal='deleted',
                short_description='A Test Project',
                delete='on'))
        r = self.app.get('/p/test/sub1/admin/overview')
        assert 'This project has been deleted and is not visible to non-admin users' in r
        assert r.html.find('input',{'name':'removal','value':'deleted'}).has_key('checked')

    def test_add_remove_trove_cat(self):
        r = self.app.get('/admin/trove')
        assert 'No Database Environment categories have been selected.' in r
        assert '<span class="trove_fullpath">Database Environment :: Database API</span>' not in r
        # add a cat
        form = r.forms['add_trove_root_database']
        form['new_trove'].value = '499'
        r = form.submit().follow()
        # make sure it worked
        assert 'No Database Environment categories have been selected.' not in r
        assert '<span class="trove_fullpath">Database Environment :: Database API</span>' in r
        # delete the cat
        r = r.forms['delete_trove_root_database_499'].submit().follow()
        # make sure it worked
        assert 'No Database Environment categories have been selected.' in r
        assert '<span class="trove_fullpath">Database Environment :: Database API</span>' not in r

    def test_add_remove_label(self):
        r = self.app.get('/admin/trove')
        form = r.forms['label_edit_form']
        form['labels'].value = 'foo,bar,baz'
        r = form.submit()
        r = r.follow()
        assert M.Project.query.get(shortname='test').labels == ['foo', 'bar', 'baz']
        assert form['labels'].value == 'foo,bar,baz'
        ThreadLocalORMSession.close_all()
        form['labels'].value = 'asdf'
        r = form.submit()
        r = r.follow()
        assert M.Project.query.get(shortname='test').labels == ['asdf']
        assert form['labels'].value == 'asdf'

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
                'card-0.id': 'admin'})
        r = self.app.get('/admin/permissions/')
        assigned_ids = [t['value'] for t in r.html.findAll('input', {'name': 'card-0.value'})]
        assert len(assigned_ids) == 2
        assert opt_developer['value'] in assigned_ids
        assert opt_admin['value'] in assigned_ids

    def test_subproject_permissions(self):    
        self.app.post('/admin/update_mounts', params={
                'new.install':'install',
                'new.ep_name':'',
                'new.ordinal':1,
                'new.mount_point':'test-subproject',
                'new.mount_label':'Test Subproject'})
        r = self.app.get('/test-subproject/admin/permissions/')
        assert len(r.html.findAll('input', {'name': 'card-0.value'})) == 0
        select = r.html.find('select', {'name': 'card-0.new'})
        opt_admin = select.find(text='Admin').parent
        opt_developer = select.find(text='Developer').parent
        assert opt_admin.name == 'option'
        assert opt_developer.name == 'option'
        r = self.app.post('/test-subproject/admin/permissions/update', params={
                'card-0.new': opt_developer['value'],
                'card-0.value': opt_admin['value'],
                'card-0.id': 'admin'})
        r = self.app.get('/test-subproject/admin/permissions/')
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

    def test_subroles(self):
        """Make sure subroles are preserved during group updates."""
        def check_roles(r):
            assert r.html.find('input', {'name': 'card-1.id'}).parent \
                         .find(text='includes the Admin group')
            assert r.html.find('input', {'name': 'card-2.id'}).parent \
                         .find(text='includes the Developer group')

        r = self.app.get('/admin/groups/')
        admin_card_id = r.html.find('input', {'name': 'card-0.id'})['value']
        dev_card_id = r.html.find('input', {'name': 'card-1.id'})['value']
        member_card_id = r.html.find('input', {'name': 'card-2.id'})['value']
        admin_id = M.User.by_username('test-admin')._id
        params = {
            'card-0.id': admin_card_id,
            'card-0.value': str(admin_id),
            'card-0.new': 'test-user',
            'card-1.id': dev_card_id,
            'card-1.value': str(admin_id),
            'card-2.id': member_card_id,
            'card-2.value': str(admin_id)
        }
        # test that subroles are intact after user added
        r = self.app.post('/admin/groups/update', params=params).follow()
        check_roles(r)
        # test that subroles are intact after user deleted
        del params['card-0.new']
        r = self.app.post('/admin/groups/update', params=params).follow()
        check_roles(r)

    def test_cannot_remove_all_admins(self):
        """Must always have at least one user with the Admin role (and anon
        doesn't count)."""
        r = self.app.get('/admin/groups/')
        admin_card_id = r.html.find('input', {'name': 'card-0.id'})['value']
        r = self.app.post('/admin/groups/update', params={
                'card-0.id': admin_card_id}).follow()
        assert 'You must have at least one user with the Admin role.' in r
        r = self.app.post('/admin/groups/update', params={
                'card-0.id': admin_card_id,
                'card-0.new': ''}).follow()
        assert 'You must have at least one user with the Admin role.' in r

    def test_cannot_add_anon_to_group(self):
        r = self.app.get('/admin/groups/')
        developer_id = r.html.find('input', {'name': 'card-1.id'})['value']
        r = self.app.post('/admin/groups/update', params={
                'card-1.id': developer_id,
                'card-1.new': ''})
        r = self.app.get('/admin/groups/')
        users = [t.previous.strip() for t in r.html.findAll('input', {'name': 'card-1.value'})]
        # no user was added
        assert len(users) == 0
        assert M.ProjectRole.query.find(dict(
                name='*anonymous', user_id=None,
                roles={'$ne': []})).count() == 0

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

        # add test-user to role
        rleNew2_id = r.html.find(text='rleNew2').findPrevious('input', {'type': 'hidden'})['value']
        r = self.app.post('/admin/groups/update', params={
                'card-1.id': rleNew2_id,
                'card-1.new': 'test-user'})

        r = self.app.post('/admin/groups/' + str(role_id) + '/update', params={'_id': role_id, 'name': 'rleNew2', 'delete': 'delete'})
        assert 'deleted' in self.webflash(r)
        r = self.app.get('/admin/groups/', status=200)
        roles = [t.string for t in r.html.findAll('h3')]
        assert 'RoleNew1' not in roles
        assert 'rleNew2' not in roles

        # make sure can still access homepage after one of user's roles were deleted
        r = self.app.get('/p/test/home/', extra_environ=dict(username='test-user')).follow()
        assert r.status == '200 OK'
