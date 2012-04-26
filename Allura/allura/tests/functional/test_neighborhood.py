import json
import os
from cStringIO import StringIO
from nose.tools import assert_raises
from datetime import datetime, timedelta

import Image
from tg import config
from nose.tools import assert_equal
from ming.orm.ormsession import ThreadLocalORMSession

import allura
from allura import model as M
from allura.tests import TestController
from allura.tests import decorators as td

class TestNeighborhood(TestController):

    def setUp(self):
        # change the override_root config value to change which root controller the test uses
        self._make_app = allura.config.middleware.make_app
        def make_app(global_conf, full_stack=True, **app_conf):
            app_conf['override_root'] = 'test_neighborhood_root'
            return self._make_app(global_conf, full_stack, **app_conf)
        allura.config.middleware.make_app = make_app
        super(TestNeighborhood, self).setUp()

    def tearDown(self):
        super(TestNeighborhood, self).tearDown()
        allura.config.middleware.make_app = self._make_app

    def test_home_project(self):
        r = self.app.get('/adobe/wiki/')
        assert r.location.endswith('/adobe/wiki/Home/')
        r = r.follow()
        assert 'Welcome' in str(r), str(r)
        r = self.app.get('/adobe/admin/', extra_environ=dict(username='test-user'),
                         status=403)

    def test_redirect(self):
        r = self.app.post('/adobe/_admin/update',
                          params=dict(redirect='wiki/Home/'),
                          extra_environ=dict(username='root'))
        r = self.app.get('/adobe/')
        assert r.location.endswith('/adobe/wiki/Home/')

    def test_admin(self):
        r = self.app.get('/adobe/_admin/', extra_environ=dict(username='root'))
        r = self.app.get('/adobe/_admin/overview', extra_environ=dict(username='root'))
        r = self.app.get('/adobe/_admin/accolades', extra_environ=dict(username='root'))
        neighborhood = M.Neighborhood.query.get(name='Adobe')
        neighborhood.features['google_analytics'] = True
        r = self.app.post('/adobe/_admin/update',
                          params=dict(name='Mozq1', css='', homepage='# MozQ1!', tracking_id='U-123456'),
                          extra_environ=dict(username='root'))
        r = self.app.post('/adobe/_admin/update',
                          params=dict(name='Mozq1', css='', homepage='# MozQ1!\n[Root]'),
                          extra_environ=dict(username='root'))
        # make sure project_template is validated as proper json
        r = self.app.post('/adobe/_admin/update',
                          params=dict(project_template='{'),
                          extra_environ=dict(username='root'))
        assert 'Invalid JSON' in r
    
    def test_admin_stats_del_count(self):
        neighborhood = M.Neighborhood.query.get(name='Adobe')
        proj = M.Project.query.get(neighborhood_id=neighborhood._id)
        proj.deleted = True
        ThreadLocalORMSession.flush_all()
        r = self.app.get('/adobe/_admin/stats/', extra_environ=dict(username='root'))
        assert 'Deleted: 1' in r
        assert 'Private: 0' in r

    def test_admin_stats_priv_count(self):
        neighborhood = M.Neighborhood.query.get(name='Adobe')
        proj = M.Project.query.get(neighborhood_id=neighborhood._id)
        proj.deleted = False
        proj.private = True
        ThreadLocalORMSession.flush_all()
        r = self.app.get('/adobe/_admin/stats/', extra_environ=dict(username='root'))
        assert 'Deleted: 0' in r
        assert 'Private: 1' in r

    def test_admin_stats_adminlist(self):
        neighborhood = M.Neighborhood.query.get(name='Adobe')
        proj = M.Project.query.get(neighborhood_id=neighborhood._id)
        proj.private = False
        ThreadLocalORMSession.flush_all()
        r = self.app.get('/adobe/_admin/stats/adminlist', extra_environ=dict(username='root'))
        pq = M.Project.query.find(dict(neighborhood_id=neighborhood._id, deleted=False))
        pq.sort('name')
        projects = pq.skip(0).limit(int(25)).all()
        for proj in projects:
            admin_role = M.ProjectRole.query.get(project_id=proj.root_project._id,name='Admin')
            if admin_role is None:
                continue
            user_role_list = M.ProjectRole.query.find(dict(project_id=proj.root_project._id, name=None)).all()
            for ur in user_role_list:
                if ur.user is not None and admin_role._id in ur.roles:
                    assert proj.name in r
                    assert ur.user.username in r

    def test_icon(self):
        file_name = 'neo-icon-set-454545-256x350.png'
        file_path = os.path.join(allura.__path__[0],'nf','allura','images',file_name)
        file_data = file(file_path).read()
        upload = ('icon', file_name, file_data)

        r = self.app.get('/adobe/_admin/', extra_environ=dict(username='root'))
        r = self.app.post('/adobe/_admin/update',
                          params=dict(name='Mozq1', css='', homepage='# MozQ1'),
                          extra_environ=dict(username='root'), upload_files=[upload])
        r = self.app.get('/adobe/icon')
        image = Image.open(StringIO(r.body))
        assert image.size == (48,48)

    def test_google_analytics(self):
        # analytics allowed
        neighborhood = M.Neighborhood.query.get(name='Adobe')
        neighborhood.features['google_analytics'] = True
        r = self.app.get('/adobe/_admin/overview', extra_environ=dict(username='root'))
        assert 'Analytics Tracking ID' in r
        r = self.app.get('/adobe/adobe-1/admin/overview', extra_environ=dict(username='root'))
        assert 'Analytics Tracking ID' in r
        r = self.app.post('/adobe/_admin/update',
                          params=dict(name='Adobe', css='', homepage='# MozQ1', tracking_id='U-123456'),
                          extra_environ=dict(username='root'))
        r = self.app.post('/adobe/adobe-1/admin/update',
                          params=dict(tracking_id='U-654321'),
                          extra_environ=dict(username='root'))
        r = self.app.get('/adobe/adobe-1/admin/overview', extra_environ=dict(username='root'))
        assert "_add_tracking('nbhd', 'U-123456');" in r
        assert "_add_tracking('proj', 'U-654321');" in r
        # analytics not allowed
        neighborhood = M.Neighborhood.query.get(name='Adobe')
        neighborhood.features['google_analytics'] = False
        r = self.app.get('/adobe/_admin/overview', extra_environ=dict(username='root'))
        assert 'Analytics Tracking ID' not in r
        r = self.app.get('/adobe/adobe-1/admin/overview', extra_environ=dict(username='root'))
        assert 'Analytics Tracking ID' not in r
        r = self.app.get('/adobe/adobe-1/admin/overview', extra_environ=dict(username='root'))
        assert "_add_tracking('nbhd', 'U-123456');" not in r
        assert "_add_tracking('proj', 'U-654321');" not in r

    def test_custom_css(self):
        test_css = '.test{color:red;}'
        custom_css = 'Custom CSS'

        neighborhood = M.Neighborhood.query.get(name='Adobe')
        neighborhood.css = test_css
        neighborhood.features['css'] = 'none'
        r = self.app.get('/adobe/')
        assert test_css not in r
        r = self.app.get('/adobe/_admin/overview', extra_environ=dict(username='root'))
        assert custom_css not in r

        neighborhood = M.Neighborhood.query.get(name='Adobe')
        neighborhood.features['css'] = 'picker'
        r = self.app.get('/adobe/')
        assert test_css in r
        r = self.app.get('/adobe/_admin/overview', extra_environ=dict(username='root'))
        assert custom_css in r

        neighborhood = M.Neighborhood.query.get(name='Adobe')
        neighborhood.features['css'] = 'custom'
        r = self.app.get('/adobe/')
        assert test_css in r
        r = self.app.get('/adobe/_admin/overview', extra_environ=dict(username='root'))
        assert custom_css in r

    def test_picker_css(self):
        neighborhood = M.Neighborhood.query.get(name='Adobe')
        neighborhood.features['css'] = 'picker'

        r = self.app.get('/adobe/_admin/overview', extra_environ=dict(username='root'))
        assert 'Project title, font' in r
        assert 'Project title, color' in r
        assert 'Bar on top' in r
        assert 'Title bar, background' in r
        assert 'Title bar, foreground' in r

        r = self.app.post('/adobe/_admin/update',
                          params={'name': 'Adobe',
                                  'css': '',
                                  'homepage': '',
                                  'css-projecttitlefont': 'arial,sans-serif',
                                  'css-projecttitlecolor': 'green',
                                  'css-barontop': '#555555',
                                  'css-titlebarbackground': '#333',
                                  'css-titlebarcolor': '#444',
                                  'css-addopt-icon-theme': 'dark'},
                          extra_environ=dict(username='root'), upload_files=[])
        neighborhood = M.Neighborhood.query.get(name='Adobe')
        assert '/*projecttitlefont*/.project_title{font-family:arial,sans-serif;}' in neighborhood.css
        assert '/*projecttitlecolor*/.project_title{color:green;}' in neighborhood.css
        assert '/*barontop*/.pad h2.colored {background-color:#555555; background-image: none;}' in neighborhood.css
        assert '/*titlebarbackground*/.pad h2.title{background-color:#333; background-image: none;}' in neighborhood.css
        assert "/*titlebarcolor*/.pad h2.title, .pad h2.title small a {color:#444;} "\
               ".pad h2.dark small b.ico {background-image: "\
               "url('/nf/_ew_/theme/allura/images/neo-icon-set-ffffff-256x350.png');}" in neighborhood.css

    def test_max_projects(self):
        # Set max value to unlimit
        neighborhood = M.Neighborhood.query.get(name='Projects')
        neighborhood.features['max_projects'] = None
        r = self.app.post('/p/register',
                          params=dict(project_unixname='maxproject1', project_name='Max project1', project_description='', neighborhood='Projects'),
                          antispam=True,
                          extra_environ=dict(username='root'), status=302)
        assert '/p/maxproject1/admin' in r.location

        # Set max value to 0
        neighborhood = M.Neighborhood.query.get(name='Projects')
        neighborhood.features['max_projects'] = 0
        r = self.app.post('/p/register',
                          params=dict(project_unixname='maxproject2', project_name='Max project2', project_description='', neighborhood='Projects'),
                          antispam=True,
                          extra_environ=dict(username='root'))
        r = r.follow()
        assert 'You have exceeded the maximum number of projects' in r

    def test_invite(self):
        p_nbhd_id = str(M.Neighborhood.query.get(name='Projects')._id)
        r = self.app.get('/adobe/_moderate/', extra_environ=dict(username='root'))
        r = self.app.post('/adobe/_moderate/invite',
                          params=dict(pid='adobe-1', invite='on', neighborhood_id=p_nbhd_id),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'error' in r
        r = self.app.post('/adobe/_moderate/invite',
                          params=dict(pid='no_such_user', invite='on', neighborhood_id=p_nbhd_id),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'error' in r
        r = self.app.post('/adobe/_moderate/invite',
                          params=dict(pid='test', invite='on', neighborhood_id=p_nbhd_id),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'invited' in r, r
        assert 'warning' not in r
        r = self.app.post('/adobe/_moderate/invite',
                          params=dict(pid='test', invite='on', neighborhood_id=p_nbhd_id),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'warning' in r
        r = self.app.post('/adobe/_moderate/invite',
                          params=dict(pid='test', uninvite='on', neighborhood_id=p_nbhd_id),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'uninvited' in r
        assert 'warning' not in r
        r = self.app.post('/adobe/_moderate/invite',
                          params=dict(pid='test', uninvite='on', neighborhood_id=p_nbhd_id),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'warning' in r
        r = self.app.post('/adobe/_moderate/invite',
                          params=dict(pid='test', invite='on', neighborhood_id=p_nbhd_id),
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
        assert 'adobe-1 evicted to Projects' in r

    def test_home(self):
        r = self.app.get('/adobe/')

    def test_register(self):
        r = self.app.get('/adobe/register', status=405)
        r = self.app.post('/adobe/register',
                          params=dict(project_unixname='', project_name='Nothing', project_description='', neighborhood='Adobe'),
                          antispam=True,
                          extra_environ=dict(username='root'))
        assert r.html.find('div',{'class':'error'}).string == 'Please enter a value'
        r = self.app.post('/adobe/register',
                          params=dict(project_unixname='mymoz', project_name='My Moz', project_description='', neighborhood='Adobe'),
                          antispam=True,
                          extra_environ=dict(username='*anonymous'),
                          status=302)
        r = self.app.post('/adobe/register',
                          params=dict(project_unixname='foo.mymoz', project_name='My Moz', project_description='', neighborhood='Adobe'),
                          antispam=True,
                          extra_environ=dict(username='root'))
        assert r.html.find('div',{'class':'error'}).string == 'Please use only letters, numbers, and dashes 3-15 characters long.'
        r = self.app.post('/p/register',
                          params=dict(project_unixname='test', project_name='Tester', project_description='', neighborhood='Projects'),
                          antispam=True,
                          extra_environ=dict(username='root'))
        assert r.html.find('div',{'class':'error'}).string == 'This project name is taken.'
        r = self.app.post('/adobe/register',
                          params=dict(project_unixname='mymoz', project_name='My Moz', project_description='', neighborhood='Adobe'),
                          antispam=True,
                          extra_environ=dict(username='root'),
                          status=302)

    def test_register_private_fails_for_anon(self):
        r = self.app.post(
            '/p/register',
            params=dict(
                project_unixname='mymoz',
                project_name='My Moz',
                project_description='',
                neighborhood='Projects',
                private_project='on'),
            antispam=True,
            extra_environ=dict(username='*anonymous'),
            status=302)
        assert config.get('auth.login_url', '/auth/') in r.location, r.location

    def test_register_private_fails_for_non_admin(self):
        self.app.post(
            '/p/register',
            params=dict(
                project_unixname='mymoz',
                project_name='My Moz',
                project_description='',
                neighborhood='Projects',
                private_project='on'),
            antispam=True,
            extra_environ=dict(username='test-user'),
            status=403)

    def test_register_private_fails_for_non_private_neighborhood(self):
        # Turn off private
        neighborhood = M.Neighborhood.query.get(name='Projects')
        neighborhood.features['private_projects'] = False
        r = self.app.get('/p/add_project', extra_environ=dict(username='root'))
        assert 'private_project' not in r

        assert_raises(ValueError,
            self.app.post,
            '/p/register',
            params=dict(
                project_unixname='myprivate1',
                project_name='My Priv1',
                project_description='',
                neighborhood='Projects',
                private_project='on'),
            antispam=True,
            extra_environ=dict(username='root'))

        proj = M.Project.query.get(shortname='myprivate1', neighborhood_id=neighborhood._id)
        assert proj is None

        # Turn on private
        neighborhood = M.Neighborhood.query.get(name='Projects')
        neighborhood.features['private_projects'] = True
        r = self.app.get('/p/add_project', extra_environ=dict(username='root'))
        assert 'private_project' in r

        self.app.post(
            '/p/register',
            params=dict(
                project_unixname='myprivate2',
                project_name='My Priv2',
                project_description='',
                neighborhood='Projects',
                private_project='on'),
            antispam=True,
            extra_environ=dict(username='root'))

        proj = M.Project.query.get(shortname='myprivate2', neighborhood_id=neighborhood._id)
        assert proj.private

    def test_register_private_ok(self):
        r = self.app.post(
            '/p/register',
            params=dict(
                project_unixname='mymoz',
                project_name='My Moz',
                project_description='',
                neighborhood='Projects',
                private_project='on',
                tools='Wiki'),
            antispam=True,
            extra_environ=dict(username='root'),
            status=302)
        assert config.get('auth.login_url', '/auth/') not in r.location, r.location
        r = self.app.get(
            '/p/mymoz/wiki/',
            extra_environ=dict(username='root')).follow(extra_environ=dict(username='root'), status=200)
        r = self.app.get(
            '/p/mymoz/wiki/',
            extra_environ=dict(username='*anonymous'),
            status=302)
        assert config.get('auth.login_url', '/auth/') in r.location, r.location
        self.app.get(
            '/p/mymoz/wiki/',
            extra_environ=dict(username='test-user'),
            status=403)

    def test_project_template(self):
        icon_url = 'file://' + os.path.join(allura.__path__[0],'nf','allura','images','neo-icon-set-454545-256x350.png')
        test_groups = [{
            "name": "Viewer", # group will be created, all params are valid
            "permissions": ["read"],
            "usernames": ["user01"]
        },{
            "name": "", # group won't be created - invalid name
            "permissions": ["read"],
            "usernames": ["user01"]
        },{
            "name": "TestGroup1", # group won't be created - invalid perm name
            "permissions": ["foobar"],
            "usernames": ["user01"]
        },{
            "name": "TestGroup2", # will be created; 'inspect' perm ignored
            "permissions": ["read", "inspect"],
            "usernames": ["user01", "user02"]
        },{
            "name": "TestGroup3", # will be created with no users in group
            "permissions": ["admin"]
        }]
        r = self.app.post('/adobe/_admin/update', params=dict(name='Mozq1',
            css='', homepage='# MozQ1!\n[Root]', project_template="""{
                "private":true,
                "icon":{
                    "url":"%s",
                    "filename":"icon.png"
                },
                "tools":{
                    "wiki":{
                        "label":"Wiki",
                        "mount_point":"wiki",
                        "options":{
                            "show_right_bar":false,
                            "show_discussion":false,
                            "some_url": "http://foo.com/$shortname/"
                        },
                        "home_text":"My home text!"
                    },
                    "discussion":{"label":"Discussion","mount_point":"discussion"},
                    "blog":{"label":"News","mount_point":"news","options":{
                    "show_discussion":false
                    }},
                    "downloads":{"label":"Downloads","mount_point":"downloads"},
                    "admin":{"label":"Admin","mount_point":"admin"}
                },
                "tool_order":["wiki","discussion","news","downloads","admin"],
                "labels":["mmi"],
                "trove_cats":{
                    "topic":[247],
                    "developmentstatus":[11]
                },
                "groups": %s
                }""" % (icon_url, json.dumps(test_groups))),
            extra_environ=dict(username='root'))
        r = self.app.post(
            '/adobe/register',
            params=dict(
                project_unixname='testtemp',
                project_name='Test Template',
                project_description='',
                neighborhood='Mozq1',
                private_project='off'),
            antispam=True,
            extra_environ=dict(username='root'),
            status=302).follow()
        p = M.Project.query.get(shortname='testtemp')
        # make sure the correct tools got installed in the right order
        top_nav = r.html.find('div',{'id':'top_nav'})
        assert top_nav.contents[1]['href'] == '/adobe/testtemp/wiki/'
        assert 'Wiki' in top_nav.contents[1].contents[0]
        assert top_nav.contents[3]['href'] == '/adobe/testtemp/discussion/'
        assert 'Discussion' in top_nav.contents[3].contents[0]
        assert top_nav.contents[5]['href'] == '/adobe/testtemp/news/'
        assert 'News' in top_nav.contents[5].contents[0]
        assert top_nav.contents[7]['href'] == '/adobe/testtemp/admin/'
        assert 'Admin' in top_nav.contents[7].contents[0]
        # make sure project is private
        r = self.app.get(
            '/adobe/testtemp/wiki/',
            extra_environ=dict(username='root')).follow(extra_environ=dict(username='root'), status=200)
        r = self.app.get(
            '/adobe/testtemp/wiki/',
            extra_environ=dict(username='*anonymous'),
            status=302)
        # check the labels and trove cats
        r = self.app.get('/adobe/testtemp/admin/trove')
        assert 'mmi' in r
        assert 'Topic :: Communications :: Telephony' in r
        assert 'Development Status :: 5 - Production/Stable' in r
        # check the wiki text
        r = self.app.get('/adobe/testtemp/wiki/').follow()
        assert "My home text!" in r
        # check tool options
        opts = p.app_config('wiki').options
        assert_equal(False, opts.show_discussion)
        assert_equal("http://foo.com/testtemp/", opts.some_url)
        # check that custom groups/perms/users were setup correctly
        roles = p.named_roles
        for group in test_groups:
            name = group.get('name')
            permissions = group.get('permissions', [])
            usernames = group.get('usernames', [])
            if name in ('Viewer', 'TestGroup2', 'TestGroup3'):
                role = M.ProjectRole.by_name(name, project=p)
                # confirm role created in project
                assert role in roles
                for perm in permissions:
                    # confirm valid permissions added to role, and invalid
                    # permissions ignored
                    if perm in p.permissions:
                        assert M.ACE.allow(role._id, perm) in p.acl
                    else:
                        assert M.ACE.allow(role._id, perm) not in p.acl
                # confirm valid users received role
                for username in usernames:
                    user = M.User.by_username(username)
                    if user and user._id:
                        assert role in user.project_role(project=p).roles
            # confirm roles with invalid json data are not created
            if name in ('', 'TestGroup1'):
                assert name not in roles


    def test_name_suggest(self):
        r = self.app.get('/p/suggest_name?project_name=My+Moz')
        assert r.json['suggested_name'] == 'mymoz'
        assert r.json['message'] == False
        r = self.app.get('/p/suggest_name?project_name=Te%st!')
        assert r.json['suggested_name'] == 'test'
        assert r.json['message'] == 'This project name is taken.'

    def test_name_check(self):
        r = self.app.get('/p/check_name?project_name=My+Moz')
        assert r.json['message'] == 'Please use only letters, numbers, and dashes 3-15 characters long.'
        r = self.app.get('/p/check_name?project_name=Te%st!')
        assert r.json['message'] == 'Please use only letters, numbers, and dashes 3-15 characters long.'
        r = self.app.get('/p/check_name?project_name=mymoz')
        assert r.json['message'] == False
        r = self.app.get('/p/check_name?project_name=test')
        assert r.json['message'] == 'This project name is taken.'

    @td.with_tool('test/sub1', 'Wiki', 'wiki')
    def test_neighborhood_project(self):
        self.app.get('/adobe/adobe-1/admin/', status=200)
        self.app.get('/p/test/sub1/wiki/')
        self.app.get('/p/test/sub1/', status=302)
        self.app.get('/p/test/no-such-app/', status=404)

    def test_neighborhood_namespace(self):
        # p/test exists, so try creating adobe/test
        self.app.get('/adobe/test/wiki/', status=404)
        r = self.app.post('/adobe/register',
                          params=dict(project_unixname='test', project_name='Test again', project_description='', neighborhood='Adobe', tools='Wiki'),
                          antispam=True,
                          extra_environ=dict(username='root'))
        assert r.status_int==302, r.html.find('div',{'class':'error'}).string
        r = self.app.get('/adobe/test/wiki/').follow(status=200)

    def test_neighborhood_awards(self):
        file_name = 'adobe_icon.png'
        file_path = os.path.join(allura.__path__[0],'public','nf','images',file_name)
        file_data = file(file_path).read()
        upload = ('icon', file_name, file_data)

        r = self.app.get('/adobe/_admin/awards', extra_environ=dict(username='root'))
        r = self.app.post('/adobe/_admin/awards/create',
                          params=dict(short='FOO', full='A basic foo award'),
                          extra_environ=dict(username='root'), upload_files=[upload])
        r = self.app.post('/adobe/_admin/awards/create',
                          params=dict(short='BAR', full='A basic bar award with no icon'),
                          extra_environ=dict(username='root'))
        foo_id = str(M.Award.query.find(dict(short='FOO')).first()._id)
        bar_id = str(M.Award.query.find(dict(short='BAR')).first()._id)
        r = self.app.post('/adobe/_admin/awards/%s/update' % bar_id,
                          params=dict(short='BAR2', full='Updated description.'),
                          extra_environ=dict(username='root')).follow().follow()
        assert 'BAR2' in r
        assert 'Updated description.' in r
        r = self.app.get('/adobe/_admin/awards/%s' % foo_id, extra_environ=dict(username='root'))
        r = self.app.get('/adobe/_admin/awards/%s/icon' % foo_id, extra_environ=dict(username='root'))
        image = Image.open(StringIO(r.body))
        assert image.size == (48,48)
        self.app.post('/adobe/_admin/awards/grant',
                          params=dict(grant='FOO', recipient='adobe-1'),
                          extra_environ=dict(username='root'))
        self.app.get('/adobe/_admin/awards/%s/adobe-1' % foo_id, extra_environ=dict(username='root'))
        self.app.post('/adobe/_admin/awards/%s/adobe-1/revoke' % foo_id,
                          extra_environ=dict(username='root'))
        self.app.post('/adobe/_admin/awards/%s/delete' % foo_id,
                          extra_environ=dict(username='root'))

    def test_add_a_project_link(self):
        r = self.app.get('/p/')
        assert 'Add a Project' in r
        r = self.app.get('/u/', extra_environ=dict(username='test-user'))
        assert 'Add a Project' not in r
        r = self.app.get('/adobe/', extra_environ=dict(username='test-user'))
        assert 'Add a Project' not in r
        r = self.app.get('/u/', extra_environ=dict(username='root'))
        assert 'Add a Project' in r
        r = self.app.get('/adobe/', extra_environ=dict(username='root'))
        assert 'Add a Project' in r

    def test_profile_topnav_menu(self):
        r = self.app.get('/u/test-user/', extra_environ=dict(username='test-user')).follow()
        assert '<a href="/u/test-user/profile/" class="ui-icon-tool-home">' in r

    def test_help(self):
        r = self.app.get('/p/_admin/help/', extra_environ=dict(username='root'))
        assert 'macro' in r
