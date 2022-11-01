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

from ming.odm import session, Mapper, ThreadLocalODMSession
from mock import patch
from tg import app_globals as g

from alluratest.controller import TestController
from allura.tests.decorators import audits, out_audits, with_user_project
from allura import model as M
from allura.scripts import delete_projects
from allura.lib import plugin


class TestDeleteProjects(TestController):

    def setup_method(self, method):
        super().setup_method(method)
        n = M.Neighborhood.query.get(name='Projects')
        admin = M.User.by_username('test-admin')
        self.p_shortname = 'test-delete'
        self.proj = n.register_project(self.p_shortname, admin)

    def run_script(self, options):
        cls = delete_projects.DeleteProjects
        opts = cls.parser().parse_args(options)
        cls.execute(opts)

    def things_related_to_project(self, pid):
        result = []
        ac_ids = [ac._id for ac in M.AppConfig.query.find(dict(project_id=pid))]
        for m in Mapper.all_mappers():
            cls = m.mapped_class
            things = None
            if 'project_id' in m.property_index:
                things = cls.query.find(dict(project_id=pid)).all()
            elif 'app_config_id' in m.property_index:
                things = cls.query.find(dict(app_config_id={'$in': ac_ids})).all()
            if things:
                result.extend(things)
        return result

    def test_project_is_deleted(self):
        p = M.Project.query.get(shortname=self.p_shortname)
        assert p is not None, 'Can not find project to delete'
        self.run_script([f'p/{p.shortname}'])
        session(p).expunge(p)
        p = M.Project.query.get(shortname=p.shortname)
        assert p is None, 'Project is not deleted'

    def test_artifacts_are_deleted(self):
        pid = M.Project.query.get(shortname=self.p_shortname)._id
        things = self.things_related_to_project(pid)
        assert len(things) > 0, 'No things related to project to begin with'
        self.run_script([f'p/{self.p_shortname}'])
        things = self.things_related_to_project(pid)
        assert len(things) == 0, 'Not all things are deleted: %s' % things

    def test_subproject_is_deleted(self):
        p = M.Project.query.get(shortname='test/sub1')
        assert p is not None, 'Can not find subproject to delete'
        self.run_script(['p/test/sub1'])
        session(p).expunge(p)
        p = M.Project.query.get(shortname='test/sub1')
        assert p is None, 'Project is not deleted'
        p = M.Project.query.get(shortname='test')
        assert p is not None, 'Parent project should not be deleted'

    def test_subproject_artifacts_are_deleted(self):
        parent_pid = M.Project.query.get(shortname='test')._id
        pid = M.Project.query.get(shortname='test/sub1')._id
        things = self.things_related_to_project(pid)
        assert len(things) > 0, 'No things related to subproject to begin with'
        parent_things_before = self.things_related_to_project(parent_pid)
        self.run_script(['p/test/sub1'])
        things = self.things_related_to_project(pid)
        assert len(things) == 0, 'Not all things are deleted: %s' % things
        parent_things_after = self.things_related_to_project(parent_pid)
        assert len(parent_things_before) == len(parent_things_after)

    @patch('allura.lib.plugin.solr_del_project_artifacts', autospec=True)
    def test_solr_index_is_deleted(self, del_solr):
        pid = M.Project.query.get(shortname=self.p_shortname)._id
        self.run_script([f'p/{self.p_shortname}'])
        del_solr.post.assert_called_once_with(pid)

    @with_user_project('test-user')
    @patch('allura.model.auth.request')
    @patch('allura.lib.helpers.request')
    def test_userproject_does_disable(self, req, req2):
        req.remote_addr = None
        req.user_agent = 'MozFoo'
        req2.url = None
        self.run_script(['u/test-user'])
        assert M.User.by_username('test-user').disabled

    @patch.object(plugin.g, 'post_event', autospec=True)
    def test_event_is_fired(self, post_event):
        pid = M.Project.query.get(shortname=self.p_shortname)._id
        self.run_script([f'p/{self.p_shortname}'])
        post_event.assert_called_once_with('project_deleted', project_id=pid, reason=None)

    @patch.object(plugin.g, 'post_event', autospec=True)
    @patch('allura.scripts.delete_projects.log', autospec=True)
    def test_delete_with_reason(self, log, post_event):
        p = M.Project.query.get(shortname=self.p_shortname)
        pid = p._id
        assert p is not None, 'Can not find project to delete'
        self.run_script(['-r', 'The Reason¢¢', f'p/{p.shortname}'])
        session(p).expunge(p)
        p = M.Project.query.get(shortname=p.shortname)
        assert p is None, 'Project is not deleted'
        log.info.assert_called_once_with('Purging %s Reason: %s', '/p/test-delete/', 'The Reason¢¢')
        post_event.assert_called_once_with('project_deleted', project_id=pid, reason='The Reason¢¢')

    def _disable_users(self, disable):
        dev = M.User.by_username('test-user')
        self.proj.add_user(dev, ['Developer'])
        ThreadLocalODMSession.flush_all()
        g.credentials.clear()
        proj = f'p/{self.p_shortname}'
        msg = f'Account disabled because project /{proj} is deleted. Reason: The Reason'
        opts = ['-r', 'The Reason', proj]
        if disable:
            opts.insert(0, '--disable-users')
        _audit = audits if disable else out_audits
        with _audit(msg, user=True):
            self.run_script(opts)
        admin = M.User.by_username('test-admin')
        dev = M.User.by_username('test-user')
        assert admin.disabled is disable
        assert dev.disabled is disable

    @patch('allura.model.auth.request')
    @patch('allura.lib.helpers.request')
    def test_disable_users(self, req, req2):
        req.remote_addr = None
        req.user_agent = 'MozFoo'
        req2.url = None
        self._disable_users(disable=True)

    def test_not_disable_users(self):
        self._disable_users(disable=False)
