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
from mock import patch

from tg import tmpl_context as c

from allura.lib import helpers as h
import allura.model as M
from allura.tests import TestController
from allura.tests.decorators import with_tool

from forgewiki.model import Page


class TestSearch(TestController):

    @patch('allura.lib.search.search')
    def test_global_search_controller(self, search):
        self.app.get('/search/')
        assert not search.called, search.called
        self.app.get('/search/', params=dict(q='Root'))
        assert search.called, search.called

    # use test2 project since 'test' project has a subproject and MockSOLR can't handle "OR" (caused by subproject)
    @with_tool('test2', 'Wiki', 'wiki')
    # include a wiki on 'test' project too though, for testing that searches are limited to correct project
    @with_tool('test', 'Wiki', 'wiki')
    def test_project_search_controller(self):
        self.app.get('/p/test2/search/')

        # add a comment
        with h.push_context('test2', 'wiki', neighborhood='Projects'):
            page = Page.find_page('Home')
            page.discussion_thread.add_post(text='Sample wiki comment')
        M.MonQTask.run_ready()

        resp = self.app.get('/p/test2/search/', params=dict(q='wiki'))
        resp.mustcontain('Welcome to your wiki! This is the default page')
        # only from this one project:
        resp.mustcontain('/test2/')
        resp.mustcontain(no='/test/')
        # nice links to comments:
        resp.mustcontain('Sample wiki comment')
        resp.mustcontain('/Home/?limit=25#')
        resp.mustcontain(no='discuss/_thread')

        # make wiki private
        with h.push_context('test2', 'wiki', neighborhood='Projects'):
            anon_role = M.ProjectRole.by_name('*anonymous')
            anon_read_perm = M.ACE.allow(anon_role._id, 'read')
            acl = c.app.config.acl
            acl.remove(anon_read_perm)

        resp = self.app.get('/p/test2/search/', params=dict(q='wiki'))
        resp.mustcontain('Welcome to your wiki! This is the default page')
        resp.mustcontain('Sample wiki comment')

        resp = self.app.get('/p/test2/search/', params=dict(q='wiki'), extra_environ=dict(username='*anonymous'))
        resp.mustcontain(no='Welcome to your wiki! This is the default page')
        resp.mustcontain(no='Sample wiki comment')
