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

from allura.tests import TestController
from allura.tests import decorators as td
from allura.lib import helpers as h


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
