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

import pkg_resources
import mock
import tg

from ming.orm import ThreadLocalORMSession, ThreadLocalODMSession
from tg import tmpl_context as c

from allura import model as M
from allura.lib import helpers as h
from allura.lib.widgets.user_profile import SectionsUtil
from allura.tests import TestController
from allura.tests import decorators as td
from alluratest.controller import setup_global_objects, setup_unit_test
from forgetracker.tests.functional.test_root import TrackerTestController


class TestPersonalDashboard(TestController):

    def test_dashboard(self):
        r = self.app.get('/dashboard')
        assert 'Test Admin / Dashboard' == r.html.find('h1', 'project_title').text.strip()
        sections = {c for s in r.html.findAll(None, 'profile-section') for c in s['class']}
        assert 'tickets' in sections
        assert 'projects' in sections
        assert 'merge_requests' in sections
        assert 'activity' in sections

    def test_dashboard_sections(self):
        def ep(n):
            m = mock.Mock()
            m.name = n
            m.load()().display.return_value = 'Section %s' % n
            return m
        eps = list(map(ep, ['a', 'b', 'c', 'd']))
        order = {'personal_dashboard_sections.order': 'b, d,c , f '}
        with mock.patch('allura.lib.helpers.iter_entry_points') as iep:
            with mock.patch.dict(tg.config, order):
                iep.return_value = eps
                sections = SectionsUtil.load_sections('personal_dashboard')
                assert sections == [
                    eps[1].load(),
                    eps[3].load(),
                    eps[2].load(),
                    eps[0].load()]
                r = self.app.get('/dashboard')
                assert 'Section a' in r.text
                assert 'Section b' in r.text
                assert 'Section c' in r.text
                assert 'Section d' in r.text
                assert 'Section f' not in r.text


class TestTicketsSection(TrackerTestController):

    @td.with_tracker
    def setup_with_tools(self):
        self.project = M.Project.query.get(shortname='test2')
        self.tracker = self.project.app_instance('bugs')
        self.new_ticket(summary='foo', _milestone='1.0', assigned_to='test-admin')

    @td.with_tool('test2', 'Tickets', 'tickets')
    def test_tickets_section(self):
        response = self.app.get('/dashboard')
        ticket_rows = response.html.find('tbody')
        assert 'foo' in str(ticket_rows)


class TestMergeRequestsSection(TestController):

    def setup_method(self, method):
        super().setup_method(method)
        setup_unit_test()
        self.setup_with_tools()
        mr= self.merge_request
        ThreadLocalODMSession.flush_all()

    # variation on @with_git but with different project to avoid clashes with other tests using git
    @td.with_tool('test2', 'Git', 'src-git', 'Git')
    def setup_with_tools(self):
        setup_global_objects()
        h.set_context('test2', 'src-git', neighborhood='Projects')
        repo_dir = pkg_resources.resource_filename(
            'forgegit', 'tests/data')
        c.app.repo.fs_path = repo_dir
        c.app.repo.name = 'testgit.git'
        self.repo = c.app.repo
        self.repo.refresh()
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    @property
    def merge_request(self):
        user = M.User.by_username('test-admin')
        project = M.Project.query.get(shortname='test')
        cid = '5c47243c8e424136fd5cdd18cd94d34c66d1955c'
        return M.MergeRequest(
            downstream={'commit_id': cid, 'project_id': project._id},
            source_branch='zz',
            target_branch='master',
            creator_id=user._id,
            request_number=1,
            summary='test request')

    def test_merge_requests_section(self):
        r = self.app.get('/dashboard')
        merge_req_rows = r.html.find('tbody')
        assert 'test request' in str(merge_req_rows)
