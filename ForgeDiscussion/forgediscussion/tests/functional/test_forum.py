# -*- coding: utf-8 -*-
import random
import logging
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart

import pkg_resources
from tg import c
from nose.tools import assert_equal

from allura import model as M
from allura.tasks import mail_tasks
from alluratest.controller import TestController
from allura.lib import helpers as h

from forgediscussion import model as FM

log = logging.getLogger(__name__)

class TestForumEmail(TestController):

    def setUp(self):
        TestController.setUp(self)
        self.app.get('/discussion/')
        r = self.app.get('/admin/discussion/forums')
        r.forms[1]['add_forum.shortname'] = 'testforum'
        r.forms[1]['add_forum.name'] = 'Test Forum'
        r.forms[1].submit()
        r = self.app.get('/admin/discussion/forums')
        assert 'testforum' in r
        self.email_address='Beta@wiki.test.projects.sourceforge.net'
        h.set_context('test', 'discussion')
        self.forum = FM.Forum.query.get(shortname='testforum')

    def test_simple_email(self):
        msg = MIMEText('This is a test message')
        self._post_email(
            self.email_address,
            [ self.forum.email_address ],
            'Test Simple Thread',
            msg)
        r = self.app.get('/p/test/discussion/testforum/')
        assert 'Test Simple Thread' in str(r), r.showbrowser()

    def test_html_email(self):
        msg = MIMEMultipart(
            'alternative',
            _subparts=[
                MIMEText('This is a test message'),
                MIMEText('This is a <em>test</em> message', 'html') ])
        self._post_email(
            self.email_address,
            [ self.forum.email_address ],
            'Test Simple Thread',
            msg)
        r = self.app.get('/p/test/discussion/testforum/')
        assert 'Test Simple Thread' in str(r), r.showbrowser()
        assert len(r.html.findAll('tr')) == 2, r.showbrowser()
        href = r.html.findAll('tr')[1].find('a')['href']
        r = self.app.get(href)
        assert 'alternate' in str(r), r.showbrowser()

    def test_html_email_with_images(self):
        msg = MIMEMultipart(
            _subparts=[
                MIMEMultipart(
                    'alternative',
                    _subparts=[
                        MIMEText('This is a test message'),
                        MIMEText('This is a <em>test</em> message', 'html')
                        ])
                ])
        with open(pkg_resources.resource_filename(
                'forgediscussion', 'tests/data/python-logo.png'), 'rb') as fp:
            img = MIMEImage(fp.read())
            img.add_header('Content-Disposition', 'attachment', filename='python-logo.png')
            msg.attach(img)
        self._post_email(
            self.email_address,
            [ self.forum.email_address ],
            'Test Simple Thread',
            msg)
        r = self.app.get('/p/test/discussion/testforum/')
        assert 'Test Simple Thread' in str(r), r.showbrowser()
        assert len(r.html.findAll('tr')) == 2, r.showbrowser()
        href = r.html.findAll('tr')[1].find('a')['href']
        r = self.app.get(href)
        assert 'alternate' in str(r), r.showbrowser()
        assert 'python-logo.png' in str(r), r.showbrowser()

    def _post_email(self, mailfrom, rcpttos, subject, msg):
        '''msg is MIME message object'''
        msg['Message-ID'] = '<' + h.gen_message_id() + '>'
        msg['From'] = mailfrom
        msg['To'] = ', '.join(rcpttos)
        msg['Subject'] = subject
        mail_tasks.route_email(
            peer='127.0.0.1',
            mailfrom=mailfrom,
            rcpttos=rcpttos,
            data=msg.as_string())
        M.artifact_orm_session.flush()

class TestForumAsync(TestController):

    def setUp(self):
        TestController.setUp(self)
        self.app.get('/discussion/')
        r = self.app.get('/admin/discussion/forums')
        r.forms[1]['add_forum.shortname'] = 'testforum'
        r.forms[1]['add_forum.name'] = 'Test Forum'
        r.forms[1].submit()
        r = self.app.get('/admin/discussion/forums')
        assert 'Test Forum' in r
        r.forms[1]['add_forum.shortname'] = 'test1'
        r.forms[1]['add_forum.name'] = 'Test Forum 1'
        r.forms[1].submit()
        r = self.app.get('/admin/discussion/forums')
        assert 'Test Forum 1' in r
        h.set_context('test', 'discussion')
        self.user_id = M.User.query.get(username='root')._id

    def test_has_access(self):
        assert True == c.app.has_access(M.User.anonymous(), 'testforum')
        assert True == c.app.has_access(M.User.query.get(username='root'), 'testforum')

    def test_post(self):
        self._post('testforum', 'Test Thread', 'Nothing here')

    def test_bad_post(self):
        self._post('Forumtest', 'Test Thread', 'Nothing here')

    def test_reply(self):
        self._post('testforum', 'Test Thread', 'Nothing here',
                   message_id='test_reply@sf.net')
        assert_equal(FM.ForumThread.query.find().count(), 1)
        assert_equal(FM.ForumPost.query.find().count(), 1)
        assert_equal(FM.ForumThread.query.get().num_replies, 1)
        assert_equal(FM.ForumThread.query.get().first_post_id, 'test_reply@sf.net')

        self._post('testforum', 'Test Reply', 'Nothing here, either',
                   message_id='test_reply1@sf.net',
                   in_reply_to=[ 'test_reply@sf.net' ])
        assert_equal(FM.ForumThread.query.find().count(), 1)
        assert_equal(FM.ForumPost.query.find().count(), 2)
        assert_equal(FM.ForumThread.query.get().first_post_id, 'test_reply@sf.net')

    def test_attach(self):
        self._post('testforum', 'Attachment Thread', 'This is a text file',
                   message_id='test.attach.100@sf.net',
                   filename='test.txt',
                   content_type='text/plain')
        self._post('testforum', 'Test Thread', 'Nothing here',
                   message_id='test.attach.100@sf.net')
        self._post('testforum', 'Attachment Thread', 'This is a text file',
                   message_id='test.attach.100@sf.net',
                   content_type='text/plain')

    def test_threads(self):
        self._post('testforum', 'Test', 'test')
        thd = FM.ForumThread.query.find().first()
        url = str('/discussion/testforum/thread/%s/' % thd._id)
        self.app.get(url)

    def test_posts(self):
        self._post('testforum', 'Test', 'test')
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
        self._post('testforum', 'Test Reply', 'Nothing here, either',
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
        message_id = kw.pop('message_id', '%s@test.com' % random.random())
        c.app.handle_message(
            topic,
            dict(kw,
                 project_id=c.project._id,
                 mount_point='discussion',
                 headers=dict(Subject=subject),
                 user_id=self.user_id,
                 payload=body,
                 message_id=message_id))
        M.artifact_orm_session.flush()

class TestForum(TestController):

    def setUp(self):
        TestController.setUp(self)
        self.app.get('/discussion/')
        r = self.app.get('/admin/discussion/forums')
        r.forms[1]['add_forum.shortname'] = 'testforum'
        r.forms[1]['add_forum.name'] = 'Test Forum'
        r.forms[1].submit()
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
        assert 'childforum' in r

    def test_unicode_name(self):
        r = self.app.get('/admin/discussion/forums')
        r.forms[1]['add_forum.shortname'] = u'téstforum'.encode('utf-8')
        r.forms[1]['add_forum.name'] = u'Tést Forum'.encode('utf-8')
        r.forms[1].submit()
        r = self.app.get('/admin/discussion/forums')
        assert u'téstforum'.encode('utf-8') in r

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
                'forum-0.shortname':'testforum',
                'forum-0.subscribed':'on',
                })
        r = self.app.post('/discussion/subscribe', params={
                'forum-0.shortname':'testforum',
                'forum-0.subscribed':'',
                })

    def test_forum_index(self):
        r = self.app.get('/discussion/testforum/')
        r = self.app.get('/discussion/testforum/childforum/')

    def test_posting(self):
        r = self.app.post('/discussion/save_new_topic', params=dict(
                subject='Test Thread',
                text='This is a *test thread*',
                forum='testforum'))
        r = self.app.get('/admin/discussion/forums')
        assert 'Message posted' in r
        r = self.app.get('/discussion/testforum/moderate/')
        n = M.Notification.query.get(text='This is a *test thread*')
        assert 'noreply' not in n.reply_to_address, n
        assert 'testforum@discussion.test.p' in n.reply_to_address, n

    def test_thread(self):
        thread = self.app.post('/discussion/save_new_topic', params=dict(
                subject='AAA',
                text='aaa',
                forum='testforum')).follow()
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

    def get_table_rows(self, response, closest_id):
        tbody = response.html.find('div', {'id': closest_id}).find('tbody')
        rows = tbody.findAll('tr')
        return rows

    def check_announcement_table(self, response, topic_name):
        assert response.html.find(text='Announcements')
        rows = self.get_table_rows(response, 'announcements')
        assert_equal(len(rows), 1)
        cell = rows[0].findAll('td', {'class': 'topic'})
        assert topic_name in str(cell)

    def test_thread_announcement(self):
        r = self.app.post('/discussion/save_new_topic', params=dict(
                subject='AAAA',
                text='aaa aaa',
                forum='testforum')).follow()
        url = r.request.url
        thread_id = url.rstrip('/').rsplit('/', 1)[-1]
        thread = FM.ForumThread.query.get(_id=thread_id)
        r = self.app.post(url + 'moderate', params=dict(
                flags='Announcement',
                discussion='testforum'))
        thread2 = FM.ForumThread.query.get(_id=thread_id)
        assert_equal(thread2.flags, ['Announcement'])

        # Check that announcements are on front discussion page
        r = self.app.get('/discussion/')
        self.check_announcement_table(r, 'AAAA')
        # Check that announcements are on each forum's page
        r = self.app.get('/discussion/testforum/')
        self.check_announcement_table(r, 'AAAA')
        r = self.app.get('/discussion/testforum/childforum/')
        self.check_announcement_table(r, 'AAAA')

    def test_thread_sticky(self):
        r = self.app.post('/discussion/save_new_topic', params=dict(
                subject='topic1',
                text='aaa aaa',
                forum='testforum')).follow()
        url1 = r.request.url
        tid1 = url1.rstrip('/').rsplit('/', 1)[-1]

        r = self.app.post('/discussion/save_new_topic', params=dict(
                subject='topic2',
                text='aaa aaa',
                forum='testforum')).follow()
        url2 = r.request.url
        tid2 = url2.rstrip('/').rsplit('/', 1)[-1]

        # Check that threads are ordered in reverse creation order
        r = self.app.get('/discussion/testforum/')
        rows = self.get_table_rows(r, 'forum_threads')
        assert_equal(len(rows), 2)
        assert 'topic2' in str(rows[0])
        assert 'topic1' in str(rows[1])

        # Make oldest thread Sticky
        r = self.app.post(url1 + 'moderate', params=dict(
                flags='Sticky',
                discussion='testforum'))
        thread1 = FM.ForumThread.query.get(_id=tid1)
        assert_equal(thread1.flags, ['Sticky'])

        # Check that Sticky thread is at the top
        r = self.app.get('/discussion/testforum/')
        rows = self.get_table_rows(r, 'forum_threads')
        assert_equal(len(rows), 2)
        assert 'topic1' in str(rows[0])
        assert 'topic2' in str(rows[1])

        # Reset Sticky flag
        r = self.app.post(url1 + 'moderate', params=dict(
                flags='',
                discussion='testforum'))
        thread1 = FM.ForumThread.query.get(_id=tid1)
        assert_equal(thread1.flags, [])

        # Would check that threads are again in reverse creation order,
        # but so far we actually sort by mod_date, and resetting a flag
        # updates it
        r = self.app.get('/discussion/testforum/')
        rows = self.get_table_rows(r, 'forum_threads')
        assert_equal(len(rows), 2)
        #assert 'topic2' in str(rows[0])
        #assert 'topic1' in str(rows[1])

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
                forum='testforum',
                subject='AAA',
                text='aaa')).follow()
        thread_sidebarmenu = str(thread.html.find('div',{'id':'sidebar'}))
        assert '<a href="flag_as_spam" class="sidebar_thread_spam"><b data-icon="^" class="ico ico-flag"></b> <span>Mark as Spam</span></a>' in thread_sidebarmenu

    def test_recent_topics_truncated(self):
        r = self.app.post('/discussion/save_new_topic', params=dict(
                forum='testforum',
                subject='This is not too long',
                text='text')).follow()
        sidebarmenu = str(r.html.find('div',{'id':'sidebar'}))
        assert 'This is not too long' in sidebarmenu
        r = self.app.post('/discussion/save_new_topic', params=dict(
                forum='testforum',
                subject='This will be truncated because it is too long to show in the sidebar without being ridiculous.',
                text='text')).follow()
        sidebarmenu = str(r.html.find('div',{'id':'sidebar'}))
        assert 'This will be truncated because it is too long to show in the sidebar ...' in sidebarmenu

    def test_feed(self):
        r = self.app.get('/discussion/general/feed', status=200)
