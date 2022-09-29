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

"""
Model tests for artifact
"""
import re
from datetime import datetime

from tg import tmpl_context as c
from mock import patch
import pytest
from ming.orm.ormsession import ThreadLocalORMSession
from ming.orm import Mapper
from bson import ObjectId
from webob import Request

import allura
from allura import model as M
from allura.lib import helpers as h
from allura.lib import security
from allura.tests import decorators as td
from allura.websetup.schema import REGISTRY
from alluratest.controller import setup_basic_test, setup_unit_test
from forgewiki import model as WM


class Checkmessage(M.Message):

    class __mongometa__:
        name = 'checkmessage'

    def url(self):
        return ''

    def __init__(self, **kw):
        super().__init__(**kw)
        if self.slug is not None and self.full_slug is None:
            self.full_slug = datetime.utcnow().strftime('%Y%m%d%H%M%S%f') + ':' + self.slug
Mapper.compile_all()


class TestArtifact:

    def setup_method(self):
        setup_basic_test()
        setup_unit_test()
        self.setup_with_tools()

    def teardown_class(cls):
        ThreadLocalORMSession.close_all()

    @td.with_wiki
    def setup_with_tools(self):
        h.set_context('test', 'wiki', neighborhood='Projects')
        Checkmessage.query.remove({})
        WM.Page.query.remove({})
        WM.PageHistory.query.remove({})
        M.Shortlink.query.remove({})
        c.user = M.User.query.get(username='test-admin')
        Checkmessage.project = c.project
        Checkmessage.app_config = c.app.config

    def test_artifact(self):
        pg = WM.Page(title='TestPage1')
        assert pg.project == c.project
        assert pg.project_id == c.project._id
        assert pg.app.config == c.app.config
        assert pg.app_config == c.app.config
        u = M.User.query.get(username='test-user')
        pr = M.ProjectRole.by_user(u, upsert=True)
        ThreadLocalORMSession.flush_all()
        REGISTRY.register(allura.credentials, allura.lib.security.Credentials())
        assert not security.has_access(pg, 'delete')(user=u)
        pg.acl.append(M.ACE.allow(pr._id, 'delete'))
        ThreadLocalORMSession.flush_all()
        assert security.has_access(pg, 'delete')(user=u)
        pg.acl.pop()
        ThreadLocalORMSession.flush_all()
        assert not security.has_access(pg, 'delete')(user=u)

    def test_artifact_index(self):
        pg = WM.Page(title='TestPage1')
        idx = pg.index()
        assert 'title' in idx
        assert 'url_s' in idx
        assert 'project_id_s' in idx
        assert 'mount_point_s' in idx
        assert 'type_s' in idx
        assert 'id' in idx
        assert idx['id'] == pg.index_id()
        assert 'text' in idx
        assert 'TestPage' in pg.shorthand_id()
        assert pg.link_text() == pg.shorthand_id()

    def test_artifactlink(self):
        pg = WM.Page(title='TestPage2')
        q_shortlink = M.Shortlink.query.find(dict(
            project_id=c.project._id,
            app_config_id=c.app.config._id,
            link=pg.shorthand_id()))
        assert q_shortlink.count() == 0

        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        assert q_shortlink.count() == 1

        assert M.Shortlink.lookup('[TestPage2]')
        assert M.Shortlink.lookup('[wiki:TestPage2]')
        assert M.Shortlink.lookup('[test:wiki:TestPage2]')
        assert not M.Shortlink.lookup('[test:wiki:TestPage2:foo]')
        assert not M.Shortlink.lookup('[Wiki:TestPage2]')
        assert not M.Shortlink.lookup('[TestPage2_no_such_page]')

        pg.delete()
        c.project.uninstall_app('wiki')
        assert not M.Shortlink.lookup('[wiki:TestPage2]')
        assert q_shortlink.count() == 0

    def test_gen_messageid(self):
        assert re.match(r'[0-9a-zA-Z]*.wiki@test.p.localhost',
                        h.gen_message_id())

    def test_gen_messageid_with_id_set(self):
        oid = ObjectId()
        assert re.match(r'%s.wiki@test.p.localhost' %
                        str(oid), h.gen_message_id(oid))

    def test_artifact_messageid(self):
        p = WM.Page(title='T')
        assert re.match(r'%s.wiki@test.p.localhost' %
                        str(p._id), p.message_id())

    def test_versioning(self):
        pg = WM.Page(title='TestPage3')
        with patch('allura.model.artifact.request', Request.blank('/', remote_addr='1.1.1.1')):
            pg.commit()
        ThreadLocalORMSession.flush_all()
        pg.text = 'Here is some text'
        pg.commit()
        ThreadLocalORMSession.flush_all()
        ss = pg.get_version(1)
        assert ss.author.logged_ip == '1.1.1.1'
        assert ss.index()['is_history_b']
        assert ss.shorthand_id() == pg.shorthand_id() + '#1'
        assert ss.title == pg.title
        assert ss.text != pg.text
        ss = pg.get_version(-1)
        assert ss.index()['is_history_b']
        assert ss.shorthand_id() == pg.shorthand_id() + '#2'
        assert ss.title == pg.title
        assert ss.text == pg.text
        pytest.raises(IndexError, pg.get_version, 42)
        pg.revert(1)
        pg.commit()
        ThreadLocalORMSession.flush_all()
        assert ss.text != pg.text
        assert pg.history().count() == 3

    def test_messages_unknown_lookup(self):
        from bson import ObjectId
        m = Checkmessage()
        m.author_id = ObjectId()  # something new
        assert isinstance(m.author(), M.User), type(m.author())
        assert m.author() == M.User.anonymous()

    @patch('allura.model.artifact.datetime')
    def test_last_updated(self, _datetime):
        c.project.last_updated = datetime(2014, 1, 1)
        _datetime.utcnow.return_value = datetime(2014, 1, 2)
        WM.Page(title='TestPage1')
        ThreadLocalORMSession.flush_all()
        assert c.project.last_updated == datetime(2014, 1, 2)

    @patch('allura.model.artifact.datetime')
    def test_last_updated_disabled(self, _datetime):
        c.project.last_updated = datetime(2014, 1, 1)
        _datetime.utcnow.return_value = datetime(2014, 1, 2)
        try:
            M.artifact_orm_session._get().skip_last_updated = True
            WM.Page(title='TestPage1')
            ThreadLocalORMSession.flush_all()
            assert c.project.last_updated == datetime(2014, 1, 1)
        finally:
            M.artifact_orm_session._get().skip_last_updated = False

    def test_get_discussion_thread_dupe(self):
        artif = WM.Page(title='TestSomeArtifact')
        thr1 = artif.get_discussion_thread()[0]
        thr1.post('thr1-post1')
        thr1.post('thr1-post2')
        thr2 = M.Thread.new(ref_id=thr1.ref_id)
        thr2.post('thr2-post1')
        thr2.post('thr2-post2')
        thr2.post('thr2-post3')
        thr3 = M.Thread.new(ref_id=thr1.ref_id)
        thr3.post('thr3-post1')
        thr4 = M.Thread.new(ref_id=thr1.ref_id)

        thread_q = M.Thread.query.find(dict(ref_id=artif.index_id()))
        assert thread_q.count() == 4

        thread = artif.get_discussion_thread()[0]  # force cleanup
        threads = thread_q.all()
        assert len(threads) == 1
        assert len(thread.posts) == 6
        # normal thread deletion propagates to children, make sure that doesn't happen
        assert not any(p.deleted for p in thread.posts)

    def test_snapshot_clear_user_data(self):
        s = M.Snapshot(author={'username': 'johndoe',
                               'display_name': 'John Doe',
                               'logged_ip': '1.2.3.4'})
        s.clear_user_data()
        assert s.author == {'username': '',
                            'display_name': '',
                            'logged_ip': None,
                            'id': None}

    def test_snapshot_from_username(self):
        s = M.Snapshot(author={'username': 'johndoe',
                               'display_name': 'John Doe',
                               'logged_ip': '1.2.3.4'})
        s = M.Snapshot(author={'username': 'johnsmith',
                               'display_name': 'John Doe',
                               'logged_ip': '1.2.3.4'})
        ThreadLocalORMSession.flush_all()
        assert len(M.Snapshot.from_username('johndoe')) == 1

    def test_feed_clear_user_data(self):
        f = M.Feed(author_name='John Doe',
                   author_link='/u/johndoe/',
                   title='Something')
        f.clear_user_data()
        assert f.author_name == ''
        assert f.author_link == ''
        assert f.title == 'Something'

        f = M.Feed(author_name='John Doe',
                   author_link='/u/johndoe/',
                   title='Home Page modified by John Doe')
        f.clear_user_data()
        assert f.author_name == ''
        assert f.author_link == ''
        assert f.title == 'Home Page modified by <REDACTED>'

    def test_feed_from_username(self):
        M.Feed(author_name='John Doe',
               author_link='/u/johndoe/',
               title='Something')
        M.Feed(author_name='John Smith',
               author_link='/u/johnsmith/',
               title='Something')
        ThreadLocalORMSession.flush_all()
        assert len(M.Feed.from_username('johndoe')) == 1

    def test_subscribed(self):
        pg = WM.Page(title='TestPage4a')
        assert pg.subscribed(include_parents=True)  # tool is subscribed to admins by default
        assert not pg.subscribed(include_parents=False)

    def test_subscribed_no_tool_sub(self):
        pg = WM.Page(title='TestPage4b')
        M.Mailbox.unsubscribe(user_id=c.user._id,
                              project_id=c.project._id,
                              app_config_id=c.app.config._id)
        pg.subscribe()
        assert pg.subscribed(include_parents=True)
        assert pg.subscribed(include_parents=False)

    def test_not_subscribed(self):
        pg = WM.Page(title='TestPage4c')
        M.Mailbox.unsubscribe(user_id=c.user._id,
                              project_id=c.project._id,
                              app_config_id=c.app.config._id)
        assert not pg.subscribed(include_parents=True)
        assert not pg.subscribed(include_parents=False)
