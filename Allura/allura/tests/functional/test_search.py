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
from ming.odm.odmsession import ThreadLocalODMSession

from tg import tmpl_context as c
from tg import app_globals as g

from allura.lib import helpers as h
import allura.model as M
from allura.tests import TestController
from allura.tests.decorators import with_tool

from forgewiki.model import Page


def _index_snapshots(*history_classes):
    """Index snapshot docs + ArtifactReferences the way `paster reindex` does.

    Snapshots never reach Solr through the normal flush path (Snapshot rows are written with
    insert_now(), which bypasses the indexing session extension), but ReindexCommand walks every
    Artifact subclass, so a reindexed deployment does have them -- along with arefs, since
    --refs is on by default.  These helpers reproduce that state.
    """
    docs = []
    for cls in history_classes:
        for snap in cls.query.find():
            doc = snap.solarize()
            if doc:
                docs.append(doc)
            M.ArtifactReference.from_artifact(snap)
    if docs:
        g.solr.add(docs)
    ThreadLocalODMSession.flush_all()


class TestSearch(TestController):

    @patch('allura.lib.search.search')
    def test_global_search_controller(self, search):
        self.app.get('/search/')
        assert not search.called, search.called
        self.app.get('/search/', params=dict(q='Root'))
        assert search.called, search.called

    @with_tool('test', 'Wiki', 'wiki')
    def test_global_search_hides_deleted_and_unmoderated(self):
        # note: the search page always echoes the raw `q` param back into the search box's
        # HTML (value="{{q}}"), so assertions below intentionally query on one marker word and
        # assert on a *different* marker word from the same text -- otherwise mustcontain(no=q)
        # would spuriously fail on the echoed query text even when actual filtering works.
        with h.push_context('test', 'wiki', neighborhood='Projects'):
            page = Page.upsert('DeleteMeSecretPage')
            page.text = 'pagequeryterm pagesecretmarker'
            page.commit()
            thread = page.discussion_thread
            post = thread.add_post(text='commentqueryterm commentsecretmarker')
            post.status = 'pending'
        ThreadLocalODMSession.flush_all()
        M.MonQTask.run_ready()

        # sanity check: live, undeleted content is normally searchable
        self.app.get('/wiki/DeleteMeSecretPage/', status=200)
        resp = self.app.get('/search/', params=dict(q='pagequeryterm'))
        resp.mustcontain('pagesecretmarker')
        # unmoderated (pending) comment text never shows, deleted or not
        resp = self.app.get('/search/', params=dict(q='commentqueryterm'))
        resp.mustcontain(no='commentsecretmarker')

        # soft-delete the page: its own page now 404s for anon, and its text should drop
        # out of search results too
        with h.push_context('test', 'wiki', neighborhood='Projects'):
            page = Page.query.get(title='DeleteMeSecretPage', app_config_id=c.app.config._id)
            page.soft_delete()
        ThreadLocalODMSession.flush_all()
        M.MonQTask.run_ready()

        self.app.get('/wiki/DeleteMeSecretPage/', extra_environ=dict(username='*anonymous'), status=404)
        resp = self.app.get('/search/', params=dict(q='pagequeryterm'))
        resp.mustcontain(no='pagesecretmarker')

    @with_tool('test', 'Wiki', 'wiki')
    def test_history_search_hides_unmoderated_comment_snapshots(self):
        # a Post Snapshot carries a copy of the comment's text but is type_s 'Post Snapshot',
        # so a filter keyed on the snapshot's own indexed fields misses it entirely
        anon = dict(username='*anonymous')
        with h.push_context('test', 'wiki', neighborhood='Projects'):
            page = Page.upsert('SnapCommentPage')
            page.text = 'ordinary page body'
            page.commit()
            post = page.discussion_thread.add_post(text='csnapquery csnapsecret')
            post.status = 'pending'
        ThreadLocalODMSession.flush_all()
        M.MonQTask.run_ready()
        _index_snapshots(M.PostHistory)

        resp = self.app.get('/search/', params=dict(q='csnapquery', history='1'), extra_environ=anon)
        resp.mustcontain(no='csnapsecret')

    @with_tool('test', 'Wiki', 'wiki')
    def test_history_search_hides_snapshots_of_deleted_pages(self):
        # snapshots indexed while the page was live keep deleted_b=False forever: soft-deleting
        # re-indexes only the page itself, so the Solr field goes stale and can't be trusted
        anon = dict(username='*anonymous')
        with h.push_context('test', 'wiki', neighborhood='Projects'):
            page = Page.upsert('SnapDeletePage')
            page.text = 'dsnapquery dsnapsecret'
            page.commit()
        ThreadLocalODMSession.flush_all()
        M.MonQTask.run_ready()
        # operator reindexes at upgrade time, while the page is still live...
        _index_snapshots(Page.__mongometa__.history_class)

        # ...and only later does someone soft-delete it
        with h.push_context('test', 'wiki', neighborhood='Projects'):
            page = Page.query.get(title='SnapDeletePage', app_config_id=c.app.config._id)
            page.soft_delete()
        ThreadLocalODMSession.flush_all()
        M.MonQTask.run_ready()

        self.app.get('/wiki/SnapDeletePage/', extra_environ=anon, status=404)
        resp = self.app.get('/search/', params=dict(q='dsnapquery', history='1'), extra_environ=anon)
        resp.mustcontain(no='dsnapsecret')

    @with_tool('test', 'Wiki', 'wiki')
    def test_history_search_still_shows_live_snapshots(self):
        # guard against over-blocking: snapshots of live, approved content must still surface
        with h.push_context('test', 'wiki', neighborhood='Projects'):
            page = Page.upsert('SnapLivePage')
            page.text = 'lsnapquery lsnapsecret'
            page.commit()
        ThreadLocalODMSession.flush_all()
        M.MonQTask.run_ready()
        _index_snapshots(Page.__mongometa__.history_class)

        resp = self.app.get('/search/', params=dict(q='lsnapquery', history='1'),
                            extra_environ=dict(username='*anonymous'))
        resp.mustcontain('lsnapsecret')

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
