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

import tempfile
import json
import os
from cgi import FieldStorage
from io import BytesIO

from tg import tmpl_context as c
from ming.orm import ThreadLocalORMSession

from allura import model as M
from allura.lib import helpers as h
from alluratest.controller import setup_basic_test, setup_global_objects
from allura.tests import decorators as td
from forgeblog import model as BM


class TestApp:

    def setup_method(self, method):
        setup_basic_test()

    @td.with_tool('test', 'Blog', 'blog')
    def test_uninstall(self):
        BM.BlogPost.new(
            title='Test title',
            text='test post',
        )
        ThreadLocalORMSession.flush_all()
        assert BM.BlogPost.query.get(title='Test title')
        # c.app.uninstall(c.project) errors out, but works ok in test_uninstall for repo tools.  So instead:
        c.project.uninstall_app('blog')
        assert not BM.BlogPost.query.get(title='Test title')

    @td.with_tool('test', 'Blog', 'blog')
    def test_sitemap_xml(self):
        assert [] == c.app.sitemap_xml()
        BM.BlogPost.new(
            title='Blog Title',
            state='draft',
            text='This is my first blog Post',
        )
        assert [] == c.app.sitemap_xml()
        BM.BlogPost.new(
            title='Blog Title',
            state='published',
            text='This is my first blog Post',
            deleted=True
        )
        assert [] == c.app.sitemap_xml()
        BM.BlogPost.new(
            title='Blog Title',
            state='published',
            text='This is my first blog Post',
        )
        assert 1 == len(c.app.sitemap_xml())


class TestBulkExport:

    def setup_method(self, method):
        setup_basic_test()
        setup_global_objects()

    @td.with_tool('test', 'Blog', 'blog')
    def test_bulk_export(self):
        # Clear out some context vars, to properly simulate how this is run from the export task
        # Besides, it's better not to need c context vars
        c.app = c.project = None

        project = M.Project.query.get(shortname='test')
        blog = project.app_instance('blog')
        with h.push_context('test', 'blog', neighborhood='Projects'):
            post = BM.BlogPost()
            post.title = 'Test title'
            post.text = 'test post'
            post.labels = ['the firstlabel', 'the second label']
            post.make_slug()
            post.commit()
            post.discussion_thread.add_post(text='test comment')
            post2 = BM.BlogPost()
            post2.title = 'Test2 title'
            post2.text = 'test2 post'
            post2.make_slug()
            post2.commit()

        f = tempfile.TemporaryFile('w+')
        blog.bulk_export(f)
        f.seek(0)
        blog = json.loads(f.read())
        blog['posts'] = sorted(
            blog['posts'], key=lambda x: x['title'], reverse=True)
        assert blog['posts'][0]['title'] == 'Test2 title'
        assert blog['posts'][0]['text'] == 'test2 post'
        assert blog['posts'][1]['title'] == 'Test title'
        assert blog['posts'][1]['text'] == 'test post'
        assert (blog['posts'][1]['labels'] ==
                     ['the firstlabel', 'the second label'])
        assert (blog['posts'][1]['discussion_thread']
                     ['posts'][0]['text'] == 'test comment')

    @td.with_tool('test', 'Blog', 'blog')
    def test_export_with_attachments(self):
        project = M.Project.query.get(shortname='test')
        blog = project.app_instance('blog')
        with h.push_context('test', 'blog', neighborhood='Projects'):
            post = BM.BlogPost.new(
                title='Test title',
                text='test post',
                labels=['the firstlabel', 'the second label'],
                delete=None
            )
            ThreadLocalORMSession.flush_all()
            test_file1 = FieldStorage()
            test_file1.name = 'file_info'
            test_file1.filename = 'test_file'
            test_file1.file = BytesIO(b'test file1\n')
            p = post.discussion_thread.add_post(text='test comment')
            p.add_multiple_attachments(test_file1)
            ThreadLocalORMSession.flush_all()
        f = tempfile.TemporaryFile('w+')
        temp_dir = tempfile.mkdtemp()
        blog.bulk_export(f, temp_dir, True)
        f.seek(0)
        blog = json.loads(f.read())
        blog['posts'] = sorted(
            blog['posts'], key=lambda x: x['title'], reverse=True)

        file_path = 'blog/{}/{}/{}/test_file'.format(
            post._id,
            post.discussion_thread._id,
            list(post.discussion_thread.post_class().query.find())[0].slug
        )
        assert (blog['posts'][0]['discussion_thread']['posts'][0]
                     ['attachments'][0]['path'] == file_path)
        assert os.path.exists(os.path.join(temp_dir, file_path))