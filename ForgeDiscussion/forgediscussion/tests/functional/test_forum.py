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

class TestForumReactors(TestController):

    def setUp(self):
        TestController.setUp(self)
        self.app.get('/discussion/')
        r = self.app.post('/admin/discussion/update_forums',
                          params={'new_forum.shortname':'testforum',
                                  'new_forum.create':'on',
                                  'new_forum.name':'Test Forum',
                                  'new_forum.description':'',
                                  'new_forum.parent':'',
                                  })
        r = self.app.get('/admin/discussion/forums')
        assert 'Test Forum' in r
        r = self.app.post('/admin/discussion/update_forums',
                          params={'new_forum.shortname':'test1',
                                  'new_forum.create':'on',
                                  'new_forum.name':'Test Forum 1',
                                  'new_forum.description':'',
                                  'new_forum.parent':'',
                                  })
        r = self.app.get('/admin/discussion/forums')
        assert 'Test Forum 1' in r
        conf_dir = getattr(config, 'here', os.getcwd())
        test_config = 'test.ini'
        test_file = os.path.join(conf_dir, test_config)
        cmd = reactor.ReactorCommand('reactor')
        cmd.args = [ test_config ]
        cmd.options = mock.Mock()
        cmd.options.dry_run = True
        cmd.options.proc = 1
        configs = cmd.command()
        self.cmd = cmd
        h.set_context('test', 'discussion')
        self.user_id = M.User.query.get(username='root')._id

    def test_has_access(self):
        assert True == c.app.has_access(M.User.anonymous(), 'test')
        assert True == c.app.has_access(M.User.query.get(username='root'), 'test')

    def test_post(self):
        self._post('discussion.msg.test forum', 'Test Thread', 'Nothing here')

    def test_bad_post(self):
        self._post('Forumtest', 'Test Thread', 'Nothing here')

    # def test_notify(self):
    #     self._post('discussion.msg.test', 'Test Thread', 'Nothing here',
    #                message_id='test_notify@sf.net')
    #     self._post('discussion.msg.test', 'Test Reply', 'Nothing here, either',
    #                message_id='test_notify1@sf.net',
    #                in_reply_to=[ 'test_notify@sf.net' ])
    #     self._notify('test_notify@sf.net')
    #     self._notify('test_notify1@sf.net')

    def test_reply(self):
        self._post('discussion.msg.testforum', 'Test Thread', 'Nothing here',
                   message_id='test_reply@sf.net')
        assert_equal(FM.ForumThread.query.find().count(), 1)
        assert_equal(FM.ForumPost.query.find().count(), 1)
        assert_equal(FM.ForumThread.query.get().num_replies, 1)
        assert_equal(FM.ForumThread.query.get().first_post_id, 'test_reply@sf.net')

        self._post('discussion.msg.testforum', 'Test Reply', 'Nothing here, either',
                   message_id='test_reply1@sf.net',
                   in_reply_to=[ 'test_reply@sf.net' ])
        assert_equal(FM.ForumThread.query.find().count(), 1)
        assert_equal(FM.ForumPost.query.find().count(), 2)
        assert_equal(FM.ForumThread.query.get().first_post_id, 'test_reply@sf.net')

    def test_attach(self):
        self._post('discussion.msg.testforum', 'Attachment Thread', 'This is a text file',
                   message_id='test.attach.100@sf.net',
                   filename='test.txt',
                   content_type='text/plain')
        self._post('discussion.msg.testforum', 'Test Thread', 'Nothing here',
                   message_id='test.attach.100@sf.net')
        self._post('discussion.msg.testforum', 'Attachment Thread', 'This is a text file',
                   message_id='test.attach.100@sf.net',
                   content_type='text/plain')

    def test_threads(self):
        self._post('discussion.msg.testforum', 'Test', 'test')
        thd = FM.ForumThread.query.find().first()
        url = str('/discussion/testforum/thread/%s/' % thd._id)
        self.app.get(url)

    def test_posts(self):
        self._post('discussion.msg.testforum', 'Test', 'test')
        thd = FM.ForumThread.query.find().first()
        thd_url = str('/discussion/testforum/thread/%s/' % thd._id)
        r = self.app.get(thd_url)
        p = FM.ForumPost.query.find().first()
        url = str('/discussion/testforum/thread/%s/%s/' % (thd._id, p.slug))
        r = self.app.get(url)
        r = self.app.post(url, params=dict(subject='New Subject', text='Asdf'))
        assert 'Asdf' in self.app.get(url)
        r = self.app.get(url, params=dict(version=1))
        r = self.app.post(url + 'reply',
                          params=dict(subject='Reply', text='text'))
        self._post('discussion.msg.testforum', 'Test Reply', 'Nothing here, either',
                   message_id='test_posts@sf.net',
                   in_reply_to=[ p._id ])
        reply = FM.ForumPost.query.get(subject='Test Reply')
        r = self.app.get(thd_url + reply.slug + '/')
        # Check attachments
        r = self.app.post(url + 'attach',
                          upload_files=[('file_info', 'test.txt', 'This is a textfile')])
        r = self.app.post(url + 'attach',
                          upload_files=[('file_info', 'test.asdfasdtxt',
                                         'This is a textfile')])
        r = self.app.get(url)
        for link in r.html.findAll('a'):
            if 'attachment' in link.get('href', ''):
                self.app.get(str(link['href']))
                self.app.post(str(link['href']), params=dict(delete='on'))
        # Moderate
        r = self.app.post(url + 'moderate',
                          params=dict(subject='New Thread', delete='', promote='on'))
        # Find new location
        r = self.app.get(url)
        link = [ a for a in r.html.findAll('a')
                 if a.renderContents() == 'here' ]
        url, slug = str(link[0]['href']).split('#')
        slug = slug.split('-')[-1]
        reply_slug = slug + str(reply.slug[4:])
        r = self.app.post(url + reply_slug + '/moderate',
                          params=dict(subject='', delete='on'))
        r = self.app.post(url + slug + '/moderate',
                          params=dict(subject='', delete='on'))

    def _post(self, topic, subject, body, **kw):
        callback = self.cmd.route_audit(topic, c.app.message_auditor)
        msg = mock.Mock()
        msg.ack = lambda:None
        msg.delivery_info = dict(routing_key=topic)
        message_id = kw.pop('message_id', '%s@test.com' % random.random())
        msg.data = dict(kw,
                        project_id=c.project._id,
                        mount_point='discussion',
                        headers=dict(Subject=subject),
                        user_id=self.user_id,
                        payload=body,
                        message_id=[message_id])
        callback(msg.data, msg)

    def _notify(self, post_id, **kw):
        callback = self.cmd.route_react('discussion.new_post', c.app.notify_subscribers)
        msg = mock.Mock()
        msg.ack = lambda:None
        msg.delivery_info = dict(routing_key='discussion.new_post')
        msg.data = dict(kw,
                        project_id=c.project._id,
                        mount_point='discussion',
                        post_id=post_id)
        callback(msg.data, msg)

class TestForum(TestController):

    def setUp(self):
        TestController.setUp(self)
        self.app.get('/discussion/')
        r = self.app.get('/admin/discussion/forums')
        r = self.app.post('/admin/discussion/update_forums',
                          params={'new_forum.shortname':'TestForum',
                                  'new_forum.create':'on',
                                  'new_forum.name':'Test Forum',
                                  'new_forum.description':'',
                                  'new_forum.parent':'',
                                  })
        r = self.app.get('/admin/discussion/forums')
        assert 'TestForum' in r
        h.set_context('test', 'discussion')
        frm = FM.Forum.query.get(shortname='TestForum')
        r = self.app.get('/admin/discussion/')
        r = self.app.post('/admin/discussion/update_forums',
                          params={'new_forum.shortname':'ChildForum',
                                  'new_forum.create':'on',
                                  'new_forum.name':'Child Forum',
                                  'new_forum.description':'',
                                  'new_forum.parent':str(frm._id),
                                  })
        r = self.app.get('/admin/discussion/forums')
        assert 'ChildForum' in r

    def test_forum_search(self):
        r = self.app.get('/discussion/search')
        r = self.app.get('/discussion/search', params=dict(q='foo'))

    def test_render_help(self):
        summary = 'test render help'
        r = self.app.get('/discussion/help')
        assert 'Forum Help' in r

    def test_render_markdown_syntax(self):
        summary = 'test render markdown syntax'
        r = self.app.get('/discussion/markdown_syntax')
        assert 'Markdown Syntax' in r

    def test_forum_subscribe(self):
        r = self.app.post('/discussion/subscribe', params={
                'forum-0.shortname':'TestForum',
                'forum-0.subscribed':'on',
                })
        r = self.app.post('/discussion/subscribe', params={
                'forum-0.shortname':'TestForum',
                'forum-0.subscribed':'',
                })

    def test_forum_index(self):
        r = self.app.get('/discussion/TestForum/')
        r = self.app.get('/discussion/TestForum/ChildForum/')

    def test_posting(self):
        r = self.app.post('/discussion/save_new_topic', params=dict(
                subject='Test Thread',
                text='This is a *test thread*',
                forum='TestForum'))
        r = self.app.get('/admin/discussion/forums')
        assert 'Message posted' in r
        r = self.app.get('/discussion/TestForum/moderate/')

    def test_thread(self):
        thread = self.app.post('/discussion/save_new_topic', params=dict(
                subject='AAA',
                text='aaa',
                forum='TestForum')).follow()
        url = thread.request.url
        rep_url = thread.html.find('div',{'class':'row reply_post_form'}).find('form').get('action')
        thread = self.app.post(str(rep_url), params=dict(
                subject='BBB',
                text='bbb'))
        thread = self.app.get(url)
        # beautiful soup is getting some unicode error here - test without it
        assert thread.html.findAll('div',{'class':'display_post'})[0].find('p').string == 'aaa'
        assert thread.html.findAll('div',{'class':'display_post'})[1].find('p').string == 'bbb'
        assert thread.response.body.count('<div class="promote_to_thread_form') == 1
        assert thread.response.body.count('<div class="row reply_post_form') == 2
        assert thread.response.body.count('<div class="edit_post_form') == 2

    def test_sidebar_menu(self):
        r = self.app.get('/discussion/')
        sidebarmenu = str(r.html.find('div',{'id':'sidebar'}))
        assert '<a href="/p/test/discussion/create_topic"><b data-icon="+" class="ico ico-plus"></b> <span>Create Topic</span></a>' in sidebarmenu
        assert '<a href="/p/test/discussion/?new_forum=True"><b data-icon="q" class="ico ico-conversation"></b> <span>Add Forum</span></a>' in sidebarmenu
        assert '<h3 class="">Help</h3>' in sidebarmenu
        assert '<a href="/p/test/discussion/help" class="nav_child"><span>Forum Help</span></a>' in sidebarmenu
        assert '<a href="/p/test/discussion/markdown_syntax" class="nav_child"><span>Markdown Syntax</span></a>' in sidebarmenu
        assert '<a href="flag_as_spam" class="sidebar_thread_spam"><b data-icon="^" class="ico ico-flag"></b> <span>Mark as Spam</span></a>' not in sidebarmenu
        thread = self.app.post('/discussion/save_new_topic', params=dict(
                forum='TestForum',
                subject='AAA',
                text='aaa')).follow()
        thread_sidebarmenu = str(thread.html.find('div',{'id':'sidebar'}))
        assert '<a href="flag_as_spam" class="sidebar_thread_spam"><b data-icon="^" class="ico ico-flag"></b> <span>Mark as Spam</span></a>' in thread_sidebarmenu

    def test_recent_topics_truncated(self):
        r = self.app.post('/discussion/save_new_topic', params=dict(
                forum='TestForum',
                subject='This is not too long',
                text='text')).follow()
        sidebarmenu = str(r.html.find('div',{'id':'sidebar'}))
        assert 'This is not too long' in sidebarmenu
        r = self.app.post('/discussion/save_new_topic', params=dict(
                forum='TestForum',
                subject='This will be truncated because it is too long to show in the sidebar without being ridiculous.',
                text='text')).follow()
        sidebarmenu = str(r.html.find('div',{'id':'sidebar'}))
        assert 'This will be truncated because it is too long to show in the sidebar ...' in sidebarmenu

class TestForumAdmin(TestController):

    def setUp(self):
        TestController.setUp(self)
        self.app.get('/discussion/')

    def test_forum_CRUD(self):
        r = self.app.get('/admin/discussion/forums')
        r = self.app.post('/admin/discussion/update_forums',
                          params={'new_forum.shortname':'TestForum',
                                  'new_forum.create':'on',
                                  'new_forum.name':'Test Forum',
                                  'new_forum.description':'',
                                  'new_forum.parent':'',
                                  })
        r = self.app.get('/admin/discussion/forums')
        assert 'TestForum' in r
        h.set_context('test', 'Forum')
        frm = FM.Forum.query.get(shortname='TestForum')
        r = self.app.post('/admin/discussion/update_forums',
                          params={'new_forum.create':'',
                                  'forum-0.delete':'',
                                  'forum-0.id':str(frm._id),
                                  'forum-0.name':'New Test Forum',
                                  'forum-0.shortname':'NewTestForum',
                                  'forum-0.description':'My desc'})
        r = self.app.get('/admin/discussion/forums')
        assert 'New Test Forum' in r
        assert 'My desc' in r

    def test_forum_CRUD_hier(self):
        r = self.app.get('/admin/discussion/forums')
        r = self.app.post('/admin/discussion/update_forums',
                          params={'new_forum.shortname':'TestForum',
                                  'new_forum.create':'on',
                                  'new_forum.name':'Test Forum',
                                  'new_forum.description':'',
                                  'new_forum.parent':'',
                                  })
        r = self.app.get('/admin/discussion/forums')
        assert 'TestForum' in r
        h.set_context('test', 'discussion')
        frm = FM.Forum.query.get(shortname='TestForum')
        r = self.app.get('/admin/discussion/forums')
        r = self.app.post('/admin/discussion/update_forums',
                          params={'new_forum.shortname':'ChildForum',
                                  'new_forum.create':'on',
                                  'new_forum.name':'Child Forum',
                                  'new_forum.description':'',
                                  'new_forum.parent':str(frm._id),
                                  })
        r = self.app.get('/admin/discussion/forums')
        assert 'ChildForum' in r

    def test_bad_forum_names(self):
        r = self.app.post('/admin/discussion/update_forums',
                          params={'new_forum.shortname':'Test.Forum',
                                  'new_forum.create':'on',
                                  'new_forum.name':'Test Forum',
                                  'new_forum.description':'',
                                  'new_forum.parent':'',
                                  })
        r = self.app.get('/admin/discussion/forums')
        assert 'error' in r
        r = self.app.post('/admin/discussion/update_forums',
                          params={'new_forum.shortname':'Test/Forum',
                                  'new_forum.create':'on',
                                  'new_forum.name':'Test Forum',
                                  'new_forum.description':'',
                                  'new_forum.parent':'',
                                  })
        r = self.app.get('/admin/discussion/forums')
        assert 'error' in r
        r = self.app.post('/admin/discussion/update_forums',
                          params={'new_forum.shortname':'Test Forum',
                                  'new_forum.create':'on',
                                  'new_forum.name':'Test Forum',
                                  'new_forum.description':'',
                                  'new_forum.parent':'',
                                  })
        r = self.app.get('/admin/discussion/forums')
        assert 'error' in r

    def test_duplicate_forum_names(self):
        self.app.post('/admin/discussion/update_forums',
                        params={'new_forum.shortname':'a',
                                'new_forum.create':'on',
                                'new_forum.name':'Forum A',
                                'new_forum.description':'',
                                'new_forum.parent':''
                               })
        self.app.post('/admin/discussion/update_forums',
                        params={'new_forum.shortname':'b',
                                'new_forum.create':'on',
                                'new_forum.name':'Forum B',
                                'new_forum.description':'',
                                'new_forum.parent':''
                               })
        h.set_context('test', 'Forum')
        forum_a = FM.Forum.query.get(shortname='a')
        self.app.post('/admin/discussion/update_forums',
                        params={'new_forum.create':'',
                                'forum-0.delete':'on',
                                'forum-0.id':str(forum_a._id),
                                'forum-0.name':'Forum A',
                                'forum-0.description':''
                               })
        # Now we have two forums: 'a', and 'b'.  'a' is deleted.
        # Let's try to create new forums with these names.
        self.app.post('/admin/discussion/update_forums',
                        params={'new_forum.shortname':'a',
                                'new_forum.create':'on',
                                'new_forum.name':'Forum A',
                                'new_forum.description':'',
                                'new_forum.parent':''
                               })
        r = self.app.get('/admin/discussion/forums')
        assert 'error' in r
        self.app.post('/admin/discussion/update_forums',
                        params={'new_forum.shortname':'b',
                                'new_forum.create':'on',
                                'new_forum.name':'Forum B',
                                'new_forum.description':'',
                                'new_forum.parent':''
                               })
        r = self.app.get('/admin/discussion/forums')
        assert 'error' in r

    def test_forum_icon(self):
        file_name = 'neo-icon-set-454545-256x350.png'
        file_path = os.path.join(allura.__path__[0],'public','nf','allura','images',file_name)
        file_data = file(file_path).read()
        upload = ('new_forum.icon', file_name, file_data)

        h.set_context('test', 'discussion')
        r = self.app.get('/admin/discussion/forums')
        r = self.app.post('/admin/discussion/update_forums',
                          params={'new_forum.shortname':'TestForum',
                                  'new_forum.create':'on',
                                  'new_forum.name':'Test Forum',
                                  'new_forum.description':'',
                                  'new_forum.parent':'',
                                  },
                          upload_files=[upload]),
        r = self.app.get('/discussion/TestForum/icon')
        image = Image.open(StringIO(r.body))
        assert image.size == (48,48)

    def test_delete_undelete(self):
        r = self.app.get('/admin/discussion/forums')
        r = self.app.post('/admin/discussion/update_forums',
                          params={'new_forum.shortname':'TestForum',
                                  'new_forum.create':'on',
                                  'new_forum.name':'Test Forum',
                                  'new_forum.description':'',
                                  'new_forum.parent':'',
                                  })
        r = self.app.get('/admin/discussion/forums')
        assert len(r.html.findAll('input',{'value':'Delete'})) == 2
        assert len(r.html.findAll('input',{'value':'Undelete'})) == 0
        r = self.app.get('/discussion/')
        assert 'This forum has been deleted and is not visible to non-admin users' not in r
        h.set_context('test', 'Forum')
        frm = FM.Forum.query.get(shortname='TestForum')

        r = self.app.post('/admin/discussion/update_forums',
                          params={'new_forum.create':'',
                                  'forum-0.delete':'on',
                                  'forum-0.id':str(frm._id),
                                  'forum-0.name':'New Test Forum',
                                  'forum-0.description':'My desc'})
        r = self.app.get('/admin/discussion/forums')
        assert len(r.html.findAll('input',{'value':'Delete'})) == 1
        assert len(r.html.findAll('input',{'value':'Undelete'})) == 1
        r = self.app.get('/discussion/')
        assert 'This forum has been deleted and is not visible to non-admin users' in r
        r = self.app.post('/admin/discussion/update_forums',
                          params={'new_forum.create':'',
                                  'forum-0.undelete':'on',
                                  'forum-0.id':str(frm._id),
                                  'forum-0.name':'New Test Forum',
                                  'forum-0.description':'My desc'})
        r = self.app.get('/admin/discussion/forums')
        assert len(r.html.findAll('input',{'value':'Delete'})) == 2
        assert len(r.html.findAll('input',{'value':'Undelete'})) == 0
        r = self.app.get('/discussion/')
        assert 'This forum has been deleted and is not visible to non-admin users' not in r
