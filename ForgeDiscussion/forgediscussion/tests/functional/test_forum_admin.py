import os
import random
import allura
import Image
from StringIO import StringIO
import logging

import mock
from tg import config
from pylons import g, c
from nose.tools import assert_equal

from ming.orm.ormsession import ThreadLocalORMSession

from alluratest.controller import TestController
from allura import model as M
from allura.command import reactor
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
        h.set_context('test', 'Forum')
        frm = FM.Forum.query.get(shortname='testforum')
        r = self.app.post('/admin/discussion/update_forums',
                          params={'forum-0.delete':'',
                                  'forum-0.id':str(frm._id),
                                  'forum-0.name':'New Test Forum',
                                  'forum-0.shortname':'NewTestForum',
                                  'forum-0.description':'My desc'})
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
        h.set_context('test', 'discussion')
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
        h.set_context('test', 'Forum')
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
        file_path = os.path.join(allura.__path__[0],'public','nf','allura','images',file_name)
        file_data = file(file_path).read()
        upload = ('add_forum.icon', file_name, file_data)

        h.set_context('test', 'discussion')
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
        h.set_context('test', 'Forum')
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
