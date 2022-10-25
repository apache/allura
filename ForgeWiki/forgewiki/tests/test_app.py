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

import datetime
import tempfile
import json
import operator
import os
from io import BytesIO

from tg import tmpl_context as c
from ming.orm import ThreadLocalORMSession

from allura import model as M
from allura.tests import decorators as td
from alluratest.controller import setup_basic_test, setup_global_objects
from forgewiki import model as WM
from forgewiki.wiki_main import ForgeWikiApp


class TestBulkExport:

    def setup_method(self, method):
        setup_basic_test()
        setup_global_objects()
        self.setup_with_tools()

    @td.with_wiki
    def setup_with_tools(self):
        self.project = M.Project.query.get(shortname='test')
        self.wiki = self.project.app_instance('wiki')
        page = WM.Page.upsert('A New Hope')
        page.text = 'Star Wars Episode IV: A New Hope'
        page.mod_date = datetime.datetime(2013, 7, 5)
        page.labels = ['star wars', 'movies']
        page.commit()
        page.discussion_thread.add_post(text='Embrace the Dark Side')
        page.discussion_thread.add_post(text='Nope')
        page = WM.Page.upsert('The Empire Strikes Back')
        page.text = 'Star Wars Episode V: The Empire Strikes Back'
        page.commit()
        page = WM.Page.upsert('Return of the Jedi')
        page.text = 'Star Wars Episode VI: Return of the Jedi'
        page.commit()
        page = WM.Page.query.get(
            app_config_id=self.wiki.config._id, title='Home')
        page.deleted = True
        page.commit()

    def test_bulk_export(self):
        # Clear out some context vars, to properly simulate how this is run from the export task
        # Besides, it's better not to need c context vars
        c.app = c.project = None

        f = tempfile.TemporaryFile('w+')
        self.wiki.bulk_export(f)
        f.seek(0)
        wiki = json.loads(f.read())
        pages = sorted(wiki['pages'], key=operator.itemgetter('title'))
        assert len(pages) == 3
        assert pages[0]['title'] == 'A New Hope'
        assert pages[0]['text'] == 'Star Wars Episode IV: A New Hope'
        assert pages[0]['mod_date'] == '2013-07-05 00:00:00'
        assert pages[0]['labels'] == ['star wars', 'movies']
        assert len(pages[0]['discussion_thread']['posts']) == 2

        assert pages[1]['title'] == 'Return of the Jedi'
        assert (pages[1]['text'] ==
                     'Star Wars Episode VI: Return of the Jedi')
        assert len(pages[1]['discussion_thread']['posts']) == 0

        assert pages[2]['title'] == 'The Empire Strikes Back'
        assert (pages[2]['text'] ==
                     'Star Wars Episode V: The Empire Strikes Back')
        assert len(pages[2]['discussion_thread']['posts']) == 0

    def add_page_with_attachmetns(self):
        self.page = WM.Page.upsert('ZTest_title')
        self.page.text = 'test_text'
        self.page.mod_date = datetime.datetime(2013, 7, 5)
        self.page.labels = ['test_label1', 'test_label2']
        self.page.attach('some/path/test_file', BytesIO(b'test string'))
        ThreadLocalORMSession.flush_all()

    def test_bulk_export_with_attachmetns(self):
        self.add_page_with_attachmetns()
        temp_dir = tempfile.mkdtemp()
        f = tempfile.TemporaryFile('w+', dir=temp_dir)
        self.wiki.bulk_export(f, temp_dir, True)
        f.seek(0)
        wiki = json.loads(f.read())
        pages = sorted(wiki['pages'], key=operator.itemgetter('title'))

        assert pages[3]['attachments'][0]['path'] == f'wiki/{self.page._id}/test_file'
        assert os.path.exists(os.path.join(temp_dir, 'wiki', str(self.page._id), 'test_file'))
        with open(os.path.join(temp_dir, 'wiki', str(self.page._id), 'test_file')) as fl:
            assert fl.read() == 'test string'

    def test_bulk_export_without_attachments(self):
        self.add_page_with_attachmetns()
        temp_dir = tempfile.mkdtemp()
        f = tempfile.TemporaryFile('w+', dir=temp_dir)
        self.wiki.bulk_export(f, temp_dir)
        f.seek(0)
        wiki = json.loads(f.read())
        pages = sorted(wiki['pages'], key=operator.itemgetter('title'))

        assert pages[3]['attachments'][0].get('path', None) is None
        assert pages[3]['attachments'][0]['url'] != f'wiki/{self.page._id}/test_file'
        assert not os.path.exists(os.path.join(temp_dir, 'wiki', str(self.page._id), 'test_file'))


class TestApp:

    def setup_method(self, method):
        setup_basic_test()
        setup_global_objects()
        self.setup_with_tools()

    @td.with_wiki
    def setup_with_tools(self):
        self.project = M.Project.query.get(shortname='test')
        self.wiki: ForgeWikiApp = self.project.app_instance('wiki')
        page = WM.Page.upsert('A New Hope')
        page.text = 'Star Wars Episode IV: A New Hope'
        page.mod_date = datetime.datetime(2013, 7, 5)
        page.labels = ['star wars', 'movies']
        page.commit()
        page.discussion_thread.add_post(text='Embrace the Dark Side')
        page.discussion_thread.add_post(text='Nope')
        page = WM.Page.upsert('The Empire Strikes Back')
        page.text = 'Star Wars Episode V: The Empire Strikes Back'
        page.commit()
        page = WM.Page.upsert('Return of the Jedi')
        page.text = 'Star Wars Episode VI: Return of the Jedi'
        page.commit()
        page = WM.Page.query.get(
            app_config_id=self.wiki.config._id, title='Home')
        page.deleted = True
        page.commit()

    def test_inbound_email(self):
        message_id = '1'
        message = 'test message'
        msg = dict(payload=message, message_id=message_id, headers={'Subject': 'test'})
        self.wiki.handle_message('A_New_Hope', msg)
        post = M.Post.query.get(_id=message_id)
        assert post["text"] == message

    def test_uninstall(self):
        assert WM.Page.query.get(title='A New Hope')
        # c.app.uninstall(c.project) errors out, but works ok in test_uninstall for repo tools.  So instead:
        c.project.uninstall_app('wiki')
        assert not WM.Page.query.get(title='A New Hope')

    def test_should_noindex_page(self):
        assert not self.wiki.should_noindex_page(None)

        assert not self.wiki.should_noindex_page(WM.Page.query.get(title='A New Hope'))

        home_page = WM.Page.query.get(title='Home')
        assert self.wiki.should_noindex_page(home_page)

        home_page.text = 'changed'
        home_page.commit()
        assert not self.wiki.should_noindex_page(home_page)

        page_default_text = WM.Page.upsert('old_default')
        page_default_text.text = 'You can edit this description'
        page_default_text.commit()
        assert self.wiki.should_noindex_page(page_default_text)

        page_default_text.discussion_thread.add_post(text='test comment')
        assert not self.wiki.should_noindex_page(page_default_text)
