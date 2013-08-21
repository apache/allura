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

#-*- python -*-

import tempfile
import json

from nose.tools import assert_equal
from pylons import tmpl_context as c

from allura import model as M
from allura.lib import helpers as h
from alluratest.controller import setup_basic_test, setup_global_objects
from allura.tests import decorators as td
from forgeblog import model as BM


class TestBulkExport(object):

    def setUp(self):
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

        f = tempfile.TemporaryFile()
        blog.bulk_export(f)
        f.seek(0)
        blog = json.loads(f.read())
        blog['posts'] = sorted(blog['posts'], key=lambda x: x['title'], reverse=True)
        assert_equal(blog['posts'][0]['title'], 'Test2 title')
        assert_equal(blog['posts'][0]['text'], 'test2 post')
        assert_equal(blog['posts'][1]['title'], 'Test title')
        assert_equal(blog['posts'][1]['text'], 'test post')
        assert_equal(blog['posts'][1]['labels'], ['the firstlabel', 'the second label'])
        assert_equal(blog['posts'][1]['discussion_thread']['posts'][0]['text'], 'test comment')
