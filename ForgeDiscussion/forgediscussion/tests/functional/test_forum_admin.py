import os
import allura
import Image
from StringIO import StringIO
import logging

from alluratest.controller import TestController
from allura.lib import helpers as h

from forgediscussion import model as FM

log = logging.getLogger(__name__)


class TestForumAdmin(TestController):

    def setUp(self):
        TestController.setUp(self)
        self.app.get('/discussion/')

    def test_forum_CRUD(self):
        r = self.app.get('/admin/discussion/forums')
        r.forms[1]['add_forum.shortname'] = 'testforum'
        r.forms[1]['add_forum.name'] = 'Test Forum'
        r = r.forms[1].submit().follow()
        assert 'Test Forum' in r
        h.set_context('test', 'Forum', neighborhood='Projects')
        frm = FM.Forum.query.get(shortname='testforum')
        r = self.app.post('/admin/discussion/update_forums',
                          params={'forum-0.delete':'',
                                  'forum-0.id':str(frm._id),
                                  'forum-0.name':'New Test Forum',
                                  'forum-0.shortname':'NewTestForum',
                                  'forum-0.description':'My desc',
                                  'forum-0.monitoring_email':''})
        r = self.app.get('/admin/discussion/forums')
        assert 'New Test Forum' in r
        assert 'My desc' in r

    def test_forum_CRUD_hier(self):
        r = self.app.get('/admin/discussion/forums')
        r.forms[1]['add_forum.shortname'] = 'testforum'
        r.forms[1]['add_forum.name'] = 'Test Forum'
        r = r.forms[1].submit().follow()
        r = self.app.get('/admin/discussion/forums')
        assert 'testforum' in r
        h.set_context('test', 'discussion', neighborhood='Projects')
        frm = FM.Forum.query.get(shortname='testforum')
        r = self.app.get('/admin/discussion/forums')
        r.forms[1]['add_forum.shortname'] = 'childforum'
        r.forms[1]['add_forum.name'] = 'Child Forum'
        r.forms[1]['add_forum.parent'] = str(frm._id)
        r.forms[1].submit()
        r = self.app.get('/admin/discussion/forums')
        assert 'Child Forum' in r

    def test_bad_forum_names(self):
        r = self.app.get('/admin/discussion/forums')
        r.forms[1]['add_forum.shortname'] = 'Test.Forum'
        r.forms[1]['add_forum.name'] = 'Test Forum'
        r = r.forms[1].submit()
        assert 'error' in r
        r = self.app.get('/admin/discussion/forums')
        r.forms[1]['add_forum.shortname'] = 'Test/Forum'
        r.forms[1]['add_forum.name'] = 'Test Forum'
        r = r.forms[1].submit()
        assert 'error' in r
        r = self.app.get('/admin/discussion/forums')
        r.forms[1]['add_forum.shortname'] = 'Test Forum'
        r.forms[1]['add_forum.name'] = 'Test Forum'
        r = r.forms[1].submit()
        assert 'error' in r

    def test_duplicate_forum_names(self):
        r = self.app.get('/admin/discussion/forums')
        r.forms[1]['add_forum.shortname'] = 'a'
        r.forms[1]['add_forum.name'] = 'Forum A'
        r = r.forms[1].submit()
        r = self.app.get('/admin/discussion/forums')
        r.forms[1]['add_forum.shortname'] = 'b'
        r.forms[1]['add_forum.name'] = 'Forum B'
        r = r.forms[1].submit()
        h.set_context('test', 'Forum', neighborhood='Projects')
        forum_a = FM.Forum.query.get(shortname='a')
        self.app.post('/admin/discussion/update_forums',
                        params={'forum-0.delete':'on',
                                'forum-0.id':str(forum_a._id),
                                'forum-0.name':'Forum A',
                                'forum-0.description':''
                               })
        # Now we have two forums: 'a', and 'b'.  'a' is deleted.
        # Let's try to create new forums with these names.
        r = self.app.get('/admin/discussion/forums')
        r.forms[1]['add_forum.shortname'] = 'a'
        r.forms[1]['add_forum.name'] = 'Forum A'
        r = r.forms[1].submit()
        assert 'error' in r
        r = self.app.get('/admin/discussion/forums')
        r.forms[1]['add_forum.shortname'] = 'b'
        r.forms[1]['add_forum.name'] = 'Forum B'
        r = r.forms[1].submit()
        assert 'error' in r

    def test_forum_icon(self):
        file_name = 'neo-icon-set-454545-256x350.png'
        file_path = os.path.join(allura.__path__[0],'nf','allura','images',file_name)
        file_data = file(file_path).read()
        upload = ('add_forum.icon', file_name, file_data)

        h.set_context('test', 'discussion', neighborhood='Projects')
        r = self.app.get('/admin/discussion/forums')
        app_id = r.forms[1]['add_forum.app_id'].value
        r = self.app.post('/admin/discussion/add_forum',
                          params={'add_forum.shortname':'testforum',
                                  'add_forum.app_id':app_id,
                                  'add_forum.name':'Test Forum',
                                  'add_forum.description':'',
                                  'add_forum.parent':'',
                                  },
                          upload_files=[upload]),
        r = self.app.get('/discussion/testforum/icon')
        image = Image.open(StringIO(r.body))
        assert image.size == (48,48)

    def test_delete_undelete(self):
        r = self.app.get('/admin/discussion/forums')
        r = self.app.get('/admin/discussion/forums')
        r.forms[1]['add_forum.shortname'] = 'testforum'
        r.forms[1]['add_forum.name'] = 'Test Forum'
        r = r.forms[1].submit()
        r = self.app.get('/admin/discussion/forums')
        assert len(r.html.findAll('input',{'value':'Delete'})) == 2
        assert len(r.html.findAll('input',{'value':'Undelete'})) == 0
        r = self.app.get('/discussion/')
        assert 'This forum has been deleted and is not visible to non-admin users' not in r
        h.set_context('test', 'Forum', neighborhood='Projects')
        frm = FM.Forum.query.get(shortname='testforum')

        r = self.app.post('/admin/discussion/update_forums',
                          params={'forum-0.delete':'on',
                                  'forum-0.id':str(frm._id),
                                  'forum-0.name':'New Test Forum',
                                  'forum-0.description':'My desc'})
        r = self.app.get('/admin/discussion/forums')
        assert len(r.html.findAll('input',{'value':'Delete'})) == 1
        assert len(r.html.findAll('input',{'value':'Undelete'})) == 1
        r = self.app.get('/discussion/')
        assert 'This forum has been deleted and is not visible to non-admin users' in r
        r = self.app.post('/admin/discussion/update_forums',
                          params={'forum-0.undelete':'on',
                                  'forum-0.id':str(frm._id),
                                  'forum-0.name':'New Test Forum',
                                  'forum-0.description':'My desc'})
        r = self.app.get('/admin/discussion/forums')
        assert len(r.html.findAll('input',{'value':'Delete'})) == 2
        assert len(r.html.findAll('input',{'value':'Undelete'})) == 0
        r = self.app.get('/discussion/')
        assert 'This forum has been deleted and is not visible to non-admin users' not in r

    def test_members_only(self):
        # make a forum anyone can see
        r = self.app.get('/admin/discussion/forums')
        r.forms[1]['add_forum.shortname'] = 'secret'
        r.forms[1]['add_forum.name'] = 'Secret'
        r.forms[1].submit()
        # forum can be viewed by member and non-member
        self.app.get('/discussion/secret')
        self.app.get('/discussion/secret',extra_environ=dict(username='test-user'))
        # make a post in the forum and confirm it is also viewable by member and non-member
        r = self.app.get('/discussion/create_topic/')
        f = r.html.find('form',{'action':'/p/test/discussion/save_new_topic'})
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_key('name'):
                params[field['name']] = field.has_key('value') and field['value'] or ''
        params[f.find('textarea')['name']] = 'secret text'
        params[f.find('select')['name']] = 'secret'
        params[f.find('input',{'style':'width: 90%'})['name']] = 'secret topic'
        r = self.app.post('/discussion/save_new_topic', params=params).follow()
        thread_url= r.request.url
        self.app.get(thread_url)
        self.app.get(thread_url,extra_environ=dict(username='test-user'))
        # link shows up in app for member and non-member
        r = self.app.get('/discussion/')
        assert '/secret/' in r
        r = self.app.get('/discussion/',extra_environ=dict(username='test-user'))
        assert '/secret/' in r
        # make the forum member only viewable
        secret = FM.Forum.query.get(shortname='secret')
        self.app.post('/admin/discussion/update_forums',
                        params={'forum-0.members_only':'on',
                                'forum-0.id':str(secret._id),
                                'forum-0.name':'Secret',
                                'forum-0.shortname':'secret',
                                'forum-0.description':'',
                                'forum-0.monitoring_email':''
                               })
        # member can see the forum, but non-member gets 403
        self.app.get('/discussion/secret')
        self.app.get('/discussion/secret',extra_environ=dict(username='test-user'), status=403)
        # member can see a thread in the forum, but non-member gets 403
        self.app.get(thread_url)
        self.app.get(thread_url,extra_environ=dict(username='test-user'), status=403)
        # link shows up in app for member but not non-member
        r = self.app.get('/discussion/')
        assert '/secret/' in r
        r = self.app.get('/discussion/',extra_environ=dict(username='test-user'))
        assert '/secret/' not in r

    def test_anon_posts(self):
        # make a forum anons can't post in
        r = self.app.get('/admin/discussion/forums')
        r.forms[1]['add_forum.shortname'] = 'testforum'
        r.forms[1]['add_forum.name'] = 'Test Forum'
        r.forms[1].submit()
        # try to post in the forum and get a 403
        r = self.app.get('/discussion/create_topic/')
        f = r.html.find('form',{'action':'/p/test/discussion/save_new_topic'})
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_key('name'):
                params[field['name']] = field.has_key('value') and field['value'] or ''
        params[f.find('textarea')['name']] = 'post text'
        params[f.find('select')['name']] = 'testforum'
        params[f.find('input',{'style':'width: 90%'})['name']] = 'post topic'
        r = self.app.post('/discussion/save_new_topic', params=params, extra_environ=dict(username='*anonymous'))
        assert r.location == 'http://localhost/auth/'
        # allow anon posts in the forum
        testforum = FM.Forum.query.get(shortname='testforum')
        self.app.post('/admin/discussion/update_forums',
                        params={'forum-0.anon_posts':'on',
                                'forum-0.id':str(testforum._id),
                                'forum-0.name':'Test Forum',
                                'forum-0.shortname':'testforum',
                                'forum-0.description':'',
                                'forum-0.monitoring_email':''
                               })
        # successfully post to the forum
        r = self.app.get('/discussion/create_topic/')
        f = r.html.find('form',{'action':'/p/test/discussion/save_new_topic'})
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_key('name'):
                params[field['name']] = field.has_key('value') and field['value'] or ''
        params[f.find('textarea')['name']] = 'post text'
        params[f.find('select')['name']] = 'testforum'
        params[f.find('input',{'style':'width: 90%'})['name']] = 'post topic'
        r = self.app.post('/discussion/save_new_topic', params=params)
        assert 'http://localhost/p/test/discussion/testforum/thread/' in r.location
