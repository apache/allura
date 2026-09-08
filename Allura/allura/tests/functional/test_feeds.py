#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

from formencode.variabledecode import variable_encode
from ming.odm import ThreadLocalODMSession

from tg import tmpl_context as c

from allura import model as M
from allura.tests import TestController
from allura.tests import decorators as td
from allura.lib import helpers as h
from forgetracker import model as TM
from forgewiki import model as WM

ANON = dict(username='*anonymous')


class TestFeeds(TestController):

    def setup_method(self, method):
        TestController.setup_method(self, method)
        self._setUp()

    @td.with_wiki
    @td.with_tracker
    def _setUp(self):
        self.app.get('/wiki/')
        self.app.get('/bugs/')
        self.app.post(
            '/bugs/save_ticket',
            params=variable_encode(dict(
                ticket_form=dict(
                    ticket_num='',
                    labels='',
                    assigned_to='',
                    milestone='',
                    summary='This is a ticket',
                    status='open',
                    description='This is a description'))),
            status=302)
        title = 'Descri\xe7\xe3o e Arquitetura'
        self.app.post(
            h.urlquote('/wiki/%s/update' % title),
            params=dict(
                title=title.encode('utf-8'),
                text="Nothing much",
                labels='',
            ),
            status=302)
        self.app.get(h.urlquote('/wiki/%s/' % title))

    def test_project_feed(self):
        self.app.get('/feed.rss')
        self.app.get('/feed.atom')

    @td.with_wiki
    def test_wiki_feed(self):
        self.app.get('/wiki/feed.rss')
        self.app.get('/wiki/feed.atom')

    @td.with_wiki
    def test_wiki_page_feed(self):
        self.app.post('/wiki/Root/update', params={
            'title': 'Root',
            'text': '',
            'labels': '',
        })
        self.app.get('/wiki/Root/feed.rss')
        self.app.get('/wiki/Root/feed.atom')

    @td.with_tracker
    def test_ticket_list_feed(self):
        self.app.get('/bugs/feed.rss')
        self.app.get('/bugs/feed.atom')

    @td.with_tracker
    @td.with_tracker
    def test_ticket_feed_drops_privatised_ticket(self):
        assert 'This is a ticket' in self.app.get('/bugs/feed.rss', extra_environ=ANON)
        TM.Ticket.query.get(ticket_num=1).private = True
        ThreadLocalODMSession.flush_all()
        r = self.app.get('/bugs/feed.rss', extra_environ=ANON)
        assert 'This is a ticket' not in r
        assert 'This is a description' not in r

    @td.with_wiki
    def test_wiki_feed_drops_deleted_page(self):
        self.app.post('/wiki/Doomed/update',
                      params={'title': 'Doomed', 'text': 'sekrit', 'labels': ''})
        assert 'sekrit' in self.app.get('/wiki/feed.rss', extra_environ=ANON)
        self.app.post('/wiki/Doomed/delete')
        assert 'sekrit' not in self.app.get('/wiki/feed.rss', extra_environ=ANON)

    @td.with_wiki
    def test_wiki_feed_drops_spammed_comment(self):
        h.set_context('test', 'wiki', neighborhood='Projects')
        page = WM.Page.query.get(title='Home', app_config_id=c.app.config._id)
        page.discussion_thread.add_post(text='spammy comment')
        ThreadLocalODMSession.flush_all()
        assert 'spammy comment' in self.app.get('/wiki/feed.rss', extra_environ=ANON)

        M.Post.query.get(text='spammy comment').spam(submit_spam_feedback=False)
        ThreadLocalODMSession.flush_all()
        assert 'spammy comment' not in self.app.get('/wiki/feed.rss', extra_environ=ANON)

        h.set_context('test', 'wiki', neighborhood='Projects')
        M.Post.query.get(text='spammy comment').undo('ok')
        ThreadLocalODMSession.flush_all()
        assert 'spammy comment' in self.app.get('/wiki/feed.rss', extra_environ=ANON)

    @td.with_wiki
    def test_wiki_feed_drops_hard_deleted_comment(self):
        h.set_context('test', 'wiki', neighborhood='Projects')
        page = WM.Page.query.get(title='Home', app_config_id=c.app.config._id)
        page.discussion_thread.add_post(text='doomed comment')
        ThreadLocalODMSession.flush_all()
        assert 'doomed comment' in self.app.get('/wiki/feed.rss', extra_environ=ANON)

        h.set_context('test', 'wiki', neighborhood='Projects')
        M.Post.query.get(text='doomed comment').delete()
        ThreadLocalODMSession.flush_all()
        assert 'doomed comment' not in self.app.get('/wiki/feed.rss', extra_environ=ANON)

    @td.with_tracker
    def test_ticket_feed(self):
        self.app.get('/bugs/1/feed.rss')
        r = self.app.get('/bugs/1/feed.atom')
        self.app.post('/bugs/1/update_ticket', params=dict(
            assigned_to='',
            ticket_num='',
            labels='',
            summary='This is a new ticket',
            status='unread',
            milestone='',
            description='This is another description'), extra_environ=dict(username='root'))
        r = self.app.get('/bugs/1/feed.atom')
        assert '=&amp;gt' in r
        assert '\n+' in r
