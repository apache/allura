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

import os
import shutil
import unittest
from unittest import skipUnless

import pkg_resources
from itertools import count, product
from datetime import datetime
from zipfile import ZipFile
from io import BytesIO
from collections import defaultdict

from tg import tmpl_context as c, app_globals as g
import mock
import tg
import ming
from ming.base import Object
from ming.orm import session, ThreadLocalORMSession
from testfixtures import TempDirectory

from alluratest.controller import setup_basic_test, setup_global_objects
from allura import model as M
from allura.model.repo_refresh import send_notifications
from allura.lib import helpers as h
from allura.webhooks import RepoPushWebhookSender
from allura.tests.model.test_repo import RepoImplTestBase

from forgesvn import model as SM
from forgesvn.model.svn import svn_path_exists
from forgesvn.tests import with_svn
from allura.tests.decorators import with_tool


class TestNewRepo(unittest.TestCase):

    def setup_method(self, method):
        setup_basic_test()
        self.setup_with_tools()

    @with_svn
    def setup_with_tools(self):
        setup_global_objects()
        h.set_context('test', 'src', neighborhood='Projects')
        repo_dir = pkg_resources.resource_filename(
            'forgesvn', 'tests/data/')
        c.app.repo.name = 'testsvn'
        c.app.repo.fs_path = repo_dir
        self.repo = c.app.repo
        self.repo.refresh()
        self.rev = self.repo.commit('HEAD')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_last_commit_for(self):
        tree = self.rev.tree
        for row in tree.ls():
            assert row['last_commit']['author'] is not None

    def test_commit(self):
        latest_rev = 7
        assert self.rev.primary() is self.rev
        assert self.rev.index_id().startswith('allura/model/repo/Commit#')
        self.rev.author_url
        self.rev.committer_url
        assert self.rev.tree._id == self.rev.tree_id
        assert self.rev.shorthand_id() == f'[r{latest_rev}]'
        assert self.rev.symbolic_ids == ([], [])
        assert self.rev.url() == f'/p/test/src/{latest_rev}/'
        all_cis = list(self.repo.log(self.rev._id, limit=25))
        assert len(all_cis) == latest_rev
        self.rev.tree.ls()
        assert self.rev.tree.readme() == ('README', 'This is readme\nAnother Line\n')
        assert self.rev.tree.path() == '/'
        assert self.rev.tree.url() == f'/p/test/src/{latest_rev}/tree/'
        self.rev.tree.by_name['README']
        assert self.rev.tree.is_blob('README') is True
        assert self.rev.tree['a']['b']['c'].ls() == []
        self.assertRaises(KeyError, lambda: self.rev.tree['a']['b']['d'])

        assert self.rev.authored_user is None
        assert self.rev.committed_user is None
        assert (
            sorted(self.rev.webhook_info.keys()) ==
            sorted(['id', 'url', 'timestamp', 'message', 'author',
                    'committer', 'added', 'removed', 'renamed', 'modified', 'copied']))


class TestSVNRepo(unittest.TestCase, RepoImplTestBase):

    def setup_method(self, method):
        setup_basic_test()
        self.setup_with_tools()

    @with_svn
    @with_tool('test', 'SVN', 'svn-tags', 'SVN with tags')
    def setup_with_tools(self):
        setup_global_objects()
        repo_dir = pkg_resources.resource_filename(
            'forgesvn', 'tests/data/')
        with h.push_context('test', 'src', neighborhood='Projects'):
            c.app.repo.name = 'testsvn'
            c.app.repo.fs_path = repo_dir
            self.repo = c.app.repo
            self.repo.refresh()
            ThreadLocalORMSession.flush_all()
            ThreadLocalORMSession.close_all()
        with h.push_context('test', 'svn-tags', neighborhood='Projects'):
            c.app.repo.name = 'testsvn-trunk-tags-branches'
            c.app.repo.fs_path = repo_dir
            self.svn_tags = c.app.repo
            self.svn_tags.refresh()
            ThreadLocalORMSession.flush_all()
            ThreadLocalORMSession.close_all()
        h.set_context('test', 'src', neighborhood='Projects')

    def test_init(self):
        repo = SM.Repository(
            name='testsvn',
            fs_path=g.tmpdir + '/',
            url_path='/test/',
            tool='svn',
            status='creating')
        dirname = os.path.join(repo.fs_path, repo.name)
        if os.path.exists(dirname):
            shutil.rmtree(dirname)
        repo.init()
        shutil.rmtree(dirname)

    def test_fork(self):
        repo = SM.Repository(
            name='testsvn',
            fs_path=g.tmpdir + '/',
            url_path='/test/',
            tool='svn',
            status='creating')
        repo_path = pkg_resources.resource_filename(
            'forgesvn', 'tests/data/testsvn')
        dirname = os.path.join(repo.fs_path, repo.name)
        if os.path.exists(dirname):
            shutil.rmtree(dirname)
        repo.init()
        repo._impl.clone_from('file://' + repo_path)
        assert not os.path.exists(
            os.path.join(g.tmpdir, 'testsvn/hooks/pre-revprop-change'))
        assert os.path.exists(
            os.path.join(g.tmpdir, 'testsvn/hooks/post-commit'))
        assert os.access(
            os.path.join(g.tmpdir, 'testsvn/hooks/post-commit'), os.X_OK)
        with open(os.path.join(g.tmpdir, 'testsvn/hooks/post-commit')) as f:
            hook_data = f.read()
        self.assertIn(
            'curl -s http://localhost/auth/refresh_repo/p/test/src/\n',
            hook_data)
        self.assertIn('exec $DIR/post-commit-user "$@"\n', hook_data)

        repo.refresh(notify=False)
        assert len(list(repo.log(limit=100)))

        shutil.rmtree(dirname)

    @mock.patch('forgesvn.model.svn.tg')
    def test_can_hotcopy(self, tg):
        from forgesvn.model.svn import SVNImplementation
        func = SVNImplementation.can_hotcopy
        obj = mock.Mock(spec=SVNImplementation)
        for combo in product(
                ['file:///myfile', 'http://myfile'],
                [True, False],
                ['version 1.7', 'version 1.6', 'version 2.0.3']):
            source_url = combo[0]
            tg.config = {'scm.svn.hotcopy': combo[1]}
            stdout = combo[2]
            obj.check_call.return_value = stdout, '', 0
            expected = (source_url.startswith('file://') and
                        tg.config['scm.svn.hotcopy'] and
                        stdout != 'version 1.6')
            result = func(obj, source_url)
            assert result == expected

    @mock.patch('forgesvn.model.svn.g.post_event')
    def test_clone(self, post_event):
        repo = SM.Repository(
            name='testsvn',
            fs_path=g.tmpdir + '/',
            url_path='/test/',
            tool='svn',
            status='creating')
        repo_path = pkg_resources.resource_filename(
            'forgesvn', 'tests/data/testsvn')
        dirname = os.path.join(repo.fs_path, repo.name)
        if os.path.exists(dirname):
            shutil.rmtree(dirname)
        repo.init()
        repo._impl.clone_from('file://' + repo_path)
        assert not os.path.exists(
            os.path.join(g.tmpdir, 'testsvn/hooks/pre-revprop-change'))
        assert os.path.exists(
            os.path.join(g.tmpdir, 'testsvn/hooks/post-commit'))
        assert os.access(
            os.path.join(g.tmpdir, 'testsvn/hooks/post-commit'), os.X_OK)
        with open(os.path.join(g.tmpdir, 'testsvn/hooks/post-commit')) as f:
            c = f.read()
        self.assertIn(
            'curl -s http://localhost/auth/refresh_repo/p/test/src/\n', c)
        self.assertIn('exec $DIR/post-commit-user "$@"\n', c)

        repo.refresh(notify=False)
        assert len(list(repo.log(limit=100)))

        shutil.rmtree(dirname)

    def test_index(self):
        i = self.repo.index()
        assert i['type_s'] == 'SVN Repository', i

    def test_log_id_only(self):
        entries = list(self.repo.log(id_only=True, limit=25))
        assert entries == [7, 6, 5, 4, 3, 2, 1]

    def test_log(self):
        entries = list(self.repo.log(id_only=False, limit=25))
        assert (entries[len(entries)-6:] ==  # only 6, so this test doesn't have to change when commits added
                [
            {'parents': [5],
             'refs': [],
             'committed': {
                 'date': datetime(2013, 11, 8, 13, 38, 11, 152821),
                 'name': 'coldmind', 'email': ''},
             'message': '',
             'rename_details': {},
             'id': 6,
             'authored': {
                 'date': datetime(2013, 11, 8, 13, 38, 11, 152821),
                 'name': 'coldmind',
                 'email': ''
            }, 'size': None},
            {'parents': [4],
             'refs': [],
             'committed': {
                 'date': datetime(2010, 11, 18, 20, 14, 21, 515743),
                 'name': 'rick446',
                 'email': ''},
             'message': 'Copied a => b',
             'rename_details': {},
             'id': 5,
             'authored': {
                 'date': datetime(2010, 11, 18, 20, 14, 21, 515743),
                 'name': 'rick446',
                 'email': ''},
             'size': None},
            {'parents': [3],
             'refs': [],
             'committed': {
                 'date': datetime(2010, 10, 8, 15, 32, 59, 383719),
                 'name': 'rick446',
                 'email': ''},
             'message': 'Remove hello.txt',
             'rename_details': {},
             'id': 4,
             'authored': {
                 'date': datetime(2010, 10, 8, 15, 32, 59, 383719),
                 'name': 'rick446',
                 'email': ''},
             'size': None},
            {'parents': [2],
             'refs': [],
             'committed': {
                 'date': datetime(2010, 10, 8, 15, 32, 48, 272296),
                 'name': 'rick446',
                 'email': ''},
             'message': 'Modify readme',
             'rename_details': {},
             'id': 3,
             'authored':
             {'date': datetime(2010, 10, 8, 15, 32, 48, 272296),
              'name': 'rick446',
              'email': ''},
             'size': None},
            {'parents': [1],
             'refs': [],
             'committed': {
                 'date': datetime(2010, 10, 8, 15, 32, 36, 221863),
                 'name': 'rick446',
                 'email': ''},
             'message': 'Add path',
             'rename_details': {},
             'id': 2,
             'authored': {
                 'date': datetime(2010, 10, 8, 15, 32, 36, 221863),
                 'name': 'rick446',
                 'email': ''},
             'size': None},
            {'parents': [],
             'refs': [],
             'committed': {
                 'date': datetime(2010, 10, 8, 15, 32, 7, 238375),
                 'name': 'rick446',
                 'email': ''},
             'message': 'Create readme',
             'rename_details': {},
             'id': 1,
             'authored': {
                 'date': datetime(2010, 10, 8, 15, 32, 7, 238375),
                 'name': 'rick446',
                 'email': ''},
             'size': None}])

    def test_log_file(self):
        entries = list(self.repo.log(path='/README', id_only=False, limit=25))
        assert entries == [
            {'authored': {'date': datetime(2010, 10, 8, 15, 32, 48, 272296),
                          'email': '',
                          'name': 'rick446'},
             'committed': {'date': datetime(2010, 10, 8, 15, 32, 48, 272296),
                           'email': '',
                           'name': 'rick446'},
             'id': 3,
             'message': 'Modify readme',
             'parents': [2],
             'refs': [],
             'size': 28,
             'rename_details': {}},
            {'authored': {'date': datetime(2010, 10, 8, 15, 32, 7, 238375),
                          'email': '',
                          'name': 'rick446'},
             'committed': {'date': datetime(2010, 10, 8, 15, 32, 7, 238375),
                           'email': '',
                           'name': 'rick446'},
             'id': 1,
             'message': 'Create readme',
             'parents': [],
             'refs': [],
             'size': 15,
             'rename_details': {}},
        ]

    def test_is_file(self):
        assert self.repo.is_file('/README')
        assert not self.repo.is_file('/a')

    def test_paged_diffs(self):
        entry = self.repo.commit(next(self.repo.log(2, id_only=True, limit=1)))
        self.assertEqual(entry.diffs, entry.paged_diffs())
        self.assertEqual(entry.diffs, entry.paged_diffs(start=0))
        added_expected = entry.diffs.added[1:3]
        expected = dict(
            copied=[], changed=[], removed=[], renamed=[],
            added=added_expected, total=4)
        actual = entry.paged_diffs(start=1, end=3)
        self.assertEqual(expected, actual)

        fake_id = self.repo._impl._oid(100)
        empty = M.repository.Commit(_id=fake_id, repo=self.repo).paged_diffs()
        self.assertEqual(sorted(actual.keys()), sorted(empty.keys()))

    def test_diff_create_file(self):
        entry = self.repo.commit(next(self.repo.log(1, id_only=True, limit=1)))
        self.assertEqual(
            entry.diffs, dict(
                copied=[], changed=[], renamed=[],
                removed=[], added=['/README'], total=1))

    def test_diff_create_path(self):
        entry = self.repo.commit(next(self.repo.log(2, id_only=True, limit=1)))
        actual = entry.diffs
        actual.added = sorted(actual.added)
        self.assertEqual(
            entry.diffs, dict(
                copied=[], changed=[], removed=[], renamed=[],
                added=sorted([
                    '/a', '/a/b', '/a/b/c',
                    '/a/b/c/hello.txt']), total=4))

    def test_diff_modify_file(self):
        entry = self.repo.commit(next(self.repo.log(3, id_only=True, limit=1)))
        self.assertEqual(
            entry.diffs, dict(
                copied=[], changed=['/README'], renamed=[],
                removed=[], added=[], total=1))

    def test_diff_delete(self):
        entry = self.repo.commit(next(self.repo.log(4, id_only=True, limit=1)))
        self.assertEqual(
            entry.diffs, dict(
                copied=[], changed=[], renamed=[],
                removed=['/a/b/c/hello.txt'], added=[], total=1))

    def test_diff_copy(self):
        entry = self.repo.commit(next(self.repo.log(5, id_only=True, limit=1)))
        assert dict(entry.diffs) == dict(
            copied=[{'new': '/b', 'old': '/a', 'ratio': 1}],  renamed=[],
            changed=[], removed=[], added=[], total=1)

    def test_commit(self):
        entry = self.repo.commit(1)
        assert entry.committed.name == 'rick446'
        assert entry.message

    def test_svn_path_exists(self):
        repo_path = pkg_resources.resource_filename(
            'forgesvn', 'tests/data/testsvn')
        assert svn_path_exists("file://%s/a" % repo_path)
        assert svn_path_exists("file://%s" % repo_path)
        assert not svn_path_exists("file://%s/badpath" % repo_path)
        with mock.patch('forgesvn.model.svn.pysvn') as pysvn:
            svn_path_exists('dummy')
            pysvn.Client.return_value.info2.assert_called_once_with(
                'dummy',
                revision=pysvn.Revision.return_value,
                recurse=False)

    @skipUnless(os.path.exists(tg.config.get('scm.repos.tarball.zip_binary', '/usr/bin/zip')), 'zip binary is missing')
    def test_tarball(self):
        tmpdir = tg.config['scm.repos.tarball.root']
        assert (self.repo.tarball_path ==
                os.path.join(tmpdir, 'svn/t/te/test/testsvn'))
        assert (self.repo.tarball_url('1') ==
                'file:///svn/t/te/test/testsvn/test-src-r1.zip')
        self.repo.tarball('1')
        assert os.path.isfile(
            os.path.join(tmpdir, "svn/t/te/test/testsvn/test-src-r1.zip"))
        tarball_zip = ZipFile(
            os.path.join(tmpdir, 'svn/t/te/test/testsvn/test-src-r1.zip'), 'r')
        assert (tarball_zip.namelist() ==
                ['test-src-r1/', 'test-src-r1/README'])
        shutil.rmtree(self.repo.tarball_path.encode('utf-8'),
                      ignore_errors=True)

    @skipUnless(os.path.exists(tg.config.get('scm.repos.tarball.zip_binary', '/usr/bin/zip')), 'zip binary is missing')
    def test_tarball_paths(self):
        rev = '19'
        h.set_context('test', 'svn-tags', neighborhood='Projects')
        tmpdir = tg.config['scm.repos.tarball.root']
        tarball_path = os.path.join(tmpdir, 'svn/t/te/test/testsvn-trunk-tags-branches/')

        # a tag
        self.svn_tags.tarball(rev, '/tags/tag-1.0/')
        fn = tarball_path + 'test-svn-tags-r19-tags-tag-1.0.zip'
        assert os.path.isfile(fn), fn
        snapshot = ZipFile(fn, 'r')
        tag_content = sorted(['test-svn-tags-r19-tags-tag-1.0/',
                              'test-svn-tags-r19-tags-tag-1.0/svn-commit.tmp',
                              'test-svn-tags-r19-tags-tag-1.0/README'])
        assert sorted(snapshot.namelist()) == tag_content
        os.remove(fn)

        # a directory (of tags)
        self.svn_tags.tarball(rev, '/tags/')
        fn = tarball_path + 'test-svn-tags-r19-tags.zip'
        assert os.path.isfile(fn), fn
        snapshot = ZipFile(fn, 'r')
        tags_content = sorted(['test-svn-tags-r19-tags/',
                               'test-svn-tags-r19-tags/tag-1.0/',
                               'test-svn-tags-r19-tags/tag-1.0/svn-commit.tmp',
                               'test-svn-tags-r19-tags/tag-1.0/README'])
        assert sorted(snapshot.namelist()) == tags_content
        os.remove(fn)

        # no path, but there are trunk in the repo
        # expect snapshot of trunk
        self.svn_tags.tarball(rev)
        fn = tarball_path + 'test-svn-tags-r19-trunk.zip'
        assert os.path.isfile(fn), fn
        snapshot = ZipFile(fn, 'r')
        trunk_content = sorted(['test-svn-tags-r19-trunk/',
                                'test-svn-tags-r19-trunk/aaa.txt',
                                'test-svn-tags-r19-trunk/bbb.txt',
                                'test-svn-tags-r19-trunk/ccc.txt',
                                'test-svn-tags-r19-trunk/README'])
        assert sorted(snapshot.namelist()) == trunk_content
        os.remove(fn)

        # no path, and no trunk dir
        # expect snapshot of repo root
        h.set_context('test', 'src', neighborhood='Projects')
        fn = os.path.join(tmpdir, 'svn/t/te/test/testsvn/test-src-r1.zip')
        self.repo.tarball('1')
        assert os.path.isfile(fn), fn
        snapshot = ZipFile(fn, 'r')
        assert snapshot.namelist() == ['test-src-r1/', 'test-src-r1/README']
        shutil.rmtree(os.path.join(tmpdir, 'svn/t/te/test/testsvn/'),
                      ignore_errors=True)
        shutil.rmtree(tarball_path, ignore_errors=True)

    def test_is_empty(self):
        assert not self.repo.is_empty()
        with TempDirectory() as d:
            repo2 = SM.Repository(
                name='test',
                fs_path=d.path,
                url_path='/test/',
                tool='svn',
                status='creating')
            repo2.init()
            assert repo2.is_empty()
            repo2.refresh()
            ThreadLocalORMSession.flush_all()
            assert repo2.is_empty()

    def test_webhook_payload(self):
        sender = RepoPushWebhookSender()
        all_commits = list(self.repo.all_commit_ids())
        start = len(all_commits) - 6  # only get a few so test doesn't have to change after new testdata commits
        cids = all_commits[start:start+2]
        payload = sender.get_payload(commit_ids=cids)
        expected_payload = {
            'size': 2,
            'after': 'r6',
            'before': 'r4',
            'commits': [{
                'id': 'r6',
                'url': 'http://localhost/p/test/src/6/',
                'timestamp': datetime(2013, 11, 8, 13, 38, 11, 152000),
                'message': '',
                'author': {'name': 'coldmind',
                           'email': '',
                           'username': ''},
                'committer': {'name': 'coldmind',
                              'email': '',
                              'username': ''},
                'added': ['/ЗРЯЧИЙ_ТА_ПОБАЧИТЬ'],
                'removed': [],
                'modified': [],
                'copied': [],
                'renamed': [],
            }, {
                'id': 'r5',
                'url': 'http://localhost/p/test/src/5/',
                'timestamp': datetime(2010, 11, 18, 20, 14, 21, 515000),
                'message': 'Copied a => b',
                'author': {'name': 'rick446',
                           'email': '',
                           'username': ''},
                'committer': {'name': 'rick446',
                              'email': '',
                              'username': ''},
                'added': [],
                'removed': [],
                'modified': [],
                'copied': [
                    {'new': '/b', 'old': '/a', 'ratio': 1},
                ],
                'renamed': [],
            }],
            'repository': {
                'name': 'SVN',
                'full_name': '/p/test/src/',
                'url': 'http://localhost/p/test/src/',
            },
        }
        assert payload == expected_payload


class TestSVNRev(unittest.TestCase):

    def setup_method(self, method):
        setup_basic_test()
        self.setup_with_tools()

    @with_svn
    def setup_with_tools(self):
        setup_global_objects()
        h.set_context('test', 'src', neighborhood='Projects')
        repo_dir = pkg_resources.resource_filename(
            'forgesvn', 'tests/data/')
        c.app.repo.name = 'testsvn'
        c.app.repo.fs_path = repo_dir
        self.repo = c.app.repo
        self.repo.refresh()
        self.rev = self.repo.commit(1)
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_url(self):
        assert self.rev.url().endswith('/1/')

    def test_primary(self):
        assert self.rev.primary() == self.rev

    def test_shorthand(self):
        assert self.rev.shorthand_id() == '[r1]'

    def test_diff(self):
        diffs = (self.rev.diffs.added
                 + self.rev.diffs.removed
                 + self.rev.diffs.changed
                 + self.rev.diffs.copied)
        for d in diffs:
            print(d)

    def _oid(self, rev_id):
        return f'{self.repo._id}:{rev_id}'

    def test_log(self):
        # path only
        commits = list(self.repo.log(self.repo.head, id_only=True, limit=25))
        assert commits == [7, 6, 5, 4, 3, 2, 1]
        commits = list(self.repo.log(self.repo.head, 'README', id_only=True, limit=25))
        assert commits == [3, 1]
        commits = list(self.repo.log(1, 'README', id_only=True, limit=25))
        assert commits == [1]
        commits = list(self.repo.log(self.repo.head, 'a/b/c/', id_only=True, limit=25))
        assert commits == [4, 2]
        commits = list(self.repo.log(3, 'a/b/c/', id_only=True, limit=25))
        assert commits == [2]
        assert (
            list(self.repo.log(self.repo.head, 'does/not/exist', id_only=True, limit=25)) == [])

    def test_notification_email(self):
        setup_global_objects()
        h.set_context('test', 'src', neighborhood='Projects')
        repo_dir = pkg_resources.resource_filename(
            'forgesvn', 'tests/data/')
        self.repo = SM.Repository(
            name='testsvn',
            fs_path=repo_dir,
            url_path='/test/',
            tool='svn',
            status='creating')
        self.repo.refresh()
        ThreadLocalORMSession.flush_all()
        send_notifications(self.repo, [self.repo.rev_to_commit_id(1)])
        ThreadLocalORMSession.flush_all()
        n = M.Notification.query.find({'subject': '[test:src] New commit [r1] by rick446'}).first()

        assert n
        assert 'By rick446' in n.text
        assert 'Create readme' in n.text


class _Test(unittest.TestCase):
    idgen = ('obj_%d' % i for i in count())

    def _make_tree(self, object_id, **kwargs):
        t, isnew = M.repository.Tree.upsert(object_id)
        repo = getattr(self, 'repo', None)
        t.repo = repo
        for k, v in kwargs.items():
            if isinstance(v, str):
                obj = M.repository.Blob(
                    t, k, next(self.idgen))
                t.blob_ids.append(Object(
                    name=k, id=obj._id))
            else:
                obj = self._make_tree(next(self.idgen), **v)
                t.tree_ids.append(Object(
                    name=k, id=obj._id))
        session(t).flush()
        return t

    def _make_commit(self, object_id, **tree_parts):
        ci, isnew = M.repository.Commit.upsert(object_id)
        if isnew:
            ci.committed.email = c.user.email_addresses[0]
            ci.authored.email = c.user.email_addresses[0]
            dt = datetime.utcnow()
            # BSON datetime resolution is to 1 millisecond, not 1 microsecond
            # like Python. Round this now so it'll match the value that's
            # pulled from MongoDB in the tests.
            ci.authored.date = dt.replace(microsecond=dt.microsecond // 1000 * 1000)
            ci.message = 'summary\n\nddescription'
            ci.set_context(self.repo)
            ci.tree_id = 't_' + object_id
            ci.tree = self._make_tree(ci.tree_id, **tree_parts)
        return ci, isnew

    def _make_log(self, ci):
        session(ci).flush(ci)

    def setup_method(self, method):
        setup_basic_test()
        setup_global_objects()
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        self.prefix = tg.config.get('scm.repos.root', '/')


class _TestWithRepo(_Test):

    def setup_method(self, method):
        super().setup_method(method)
        h.set_context('test', neighborhood='Projects')
        c.project.install_app('svn', 'test1')
        h.set_context('test', 'test1', neighborhood='Projects')
        self.repo = M.Repository(name='test1', tool='svn')
        self.repo._impl = mock.Mock()
        self.repo._impl.shorthand_for_commit = M.RepositoryImplementation.shorthand_for_commit
        self.repo._impl.url_for_commit = (
            lambda *a, **kw: M.RepositoryImplementation.url_for_commit(
                self.repo._impl, *a, **kw))
        self.repo._impl._repo = self.repo
        self.repo._impl.all_commit_ids = lambda *a, **kw: []
        self.repo._impl.commit().symbolic_ids = None
        ThreadLocalORMSession.flush_all()


class _TestWithRepoAndCommit(_TestWithRepo):

    def setup_method(self, method):
        super().setup_method(method)
        self.ci, isnew = self._make_commit('foo')
        ThreadLocalORMSession.flush_all()
        # ThreadLocalORMSession.close_all()


class TestRepo(_TestWithRepo):

    def test_create(self):
        assert self.repo.fs_path == os.path.join(self.prefix, 'svn/p/test/')
        assert self.repo.url_path == '/p/test/'
        assert self.repo.full_fs_path == os.path.join(
            self.prefix, 'svn/p/test/test1')

    def test_passthrough(self):
        argless = ['init']
        for fn in argless:
            getattr(self.repo, fn)()
            getattr(self.repo._impl, fn).assert_called_with()
        unary = ['commit', 'open_blob']
        for fn in unary:
            getattr(self.repo, fn)('foo')
            getattr(self.repo._impl, fn).assert_called_with('foo')

    def test_shorthand_for_commit(self):
        self.assertEqual(
            self.repo.shorthand_for_commit('a' * 40),
            '[aaaaaa]')

    def test_url_for_commit(self):
        self.assertEqual(
            self.repo.url_for_commit('a' * 40),
            '/p/test/test1/ci/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/')

    @mock.patch('allura.model.repository.g.post_event')
    def test_init_as_clone(self, post_event):
        self.repo.init_as_clone('srcpath', 'srcname', 'srcurl')
        assert self.repo.upstream_repo.name == 'srcname'
        assert self.repo.upstream_repo.url == 'srcurl'
        assert self.repo._impl.clone_from.called_with('srcpath')
        post_event.assert_called_once_with('repo_cloned', 'srcurl', 'srcpath')

    def test_latest(self):
        ci = mock.Mock()
        self.repo._impl.commit = mock.Mock(return_value=ci)
        assert self.repo.latest() is ci

    def test_index(self):
        i = self.repo.index()
        assert i['type_s'] == 'Repository', i
        assert i['name_s'] == 'test1', i

    def test_scm_host_url(self):
        assert (self.repo.clone_url('rw', 'nobody') ==
                'svn+ssh://nobody@localhost:8022/scm-repo/p/test/test1/')
        assert (self.repo.clone_url('https', 'nobody') ==
                'https://nobody@localhost:8022/scm-repo/p/test/test1/')
        with h.push_config(self.repo.app.config.options, external_checkout_url='https://$username@foo.com/'):
            assert (self.repo.clone_url('https', 'user') ==
                    'https://user@foo.com/')

    def test_guess_type(self):
        assert self.repo.guess_type('foo.txt') == ('text/plain', None)
        assert self.repo.guess_type('foo.gbaer') == (
            'application/octet-stream', None)
        assert self.repo.guess_type('foo.html') == ('text/html', None)
        assert self.repo.guess_type('.gitignore') == ('text/plain', None)

    def test_refresh(self):
        committer_name = 'Test Committer'
        committer_email = 'test@example.com'
        ci = mock.Mock()
        ci.authored.name = committer_name
        ci.committed.name = committer_name
        ci.committed.email = committer_email
        ci.author_url = '/u/test-committer/'
        ci.activity_name = '[deadbeef]'
        ci.activity_url = 'url'
        ci.activity_extras = {}
        del ci.node_id
        self.repo._impl.commit = mock.Mock(return_value=ci)
        self.repo._impl.new_commits = mock.Mock(
            return_value=['foo%d' % i for i in range(100)])
        self.repo._impl.all_commit_ids = mock.Mock(
            return_value=['foo%d' % i for i in range(100)])
        self.repo.symbolics_for_commit = mock.Mock(
            return_value=[['master', 'branch'], []])

        def refresh_commit_info(oid, seen, lazy=False):
            M.repository.CommitDoc(dict(
                authored=dict(
                    name=committer_name,
                    date=datetime(2010, 10, 8, 15, 32, 48, 0),
                    email=committer_email),
                _id=oid)).m.insert()
        self.repo._impl.refresh_commit_info = refresh_commit_info
        def _id(oid): return getattr(oid, '_id', str(oid))
        self.repo.shorthand_for_commit = lambda oid: '[' + _id(oid) + ']'
        self.repo.url_for_commit = lambda oid: '/ci/' + _id(oid) + '/'
        self.repo.refresh()
        ThreadLocalORMSession.flush_all()
        notifications = M.Notification.query.find().all()
        for n in notifications:
            if '100 new commits' in n.subject:
                assert 'By Test Committer on 10/08/2010 15:32' in n.text
                assert 'http://localhost/ci/foo99/' in n.text
                break
        else:
            assert False, 'Did not find notification'
        assert M.Feed.query.find(dict(
            author_name=committer_name)).count() == 100

    def test_refresh_private(self):
        ci = mock.Mock()
        self.repo._impl.commit = mock.Mock(return_value=ci)
        self.repo._impl.new_commits = mock.Mock(
            return_value=['foo%d' % i for i in range(100)])

        # make unreadable by *anonymous, so additional notification logic
        # executes
        self.repo.acl = []
        c.project.acl = []

        self.repo.refresh()

    def test_push_upstream_context(self):
        self.repo.init_as_clone('srcpath', '/p/test/svn/', '/p/test/svn/')
        old_app_instance = M.Project.app_instance
        try:
            M.Project.app_instance = mock.Mock(return_value=ming.base.Object(
                config=ming.base.Object(_id=None)))
            with self.repo.push_upstream_context():
                assert c.project.shortname == 'test'
        finally:
            M.Project.app_instance = old_app_instance

    def test_pending_upstream_merges(self):
        self.repo.init_as_clone('srcpath', '/p/test/svn/', '/p/test/svn/')
        old_app_instance = M.Project.app_instance
        try:
            M.Project.app_instance = mock.Mock(return_value=ming.base.Object(
                config=ming.base.Object(_id=None)))
            self.repo.pending_upstream_merges()
        finally:
            M.Project.app_instance = old_app_instance


class TestRepoObject(_TestWithRepoAndCommit):

    def test_upsert(self):
        obj0, isnew0 = M.repository.Tree.upsert('foo1')
        obj1, isnew1 = M.repository.Tree.upsert('foo1')
        assert obj0 is obj1
        assert isnew0 and not isnew1

    def test_artifact_methods(self):
        assert self.ci.index_id(
        ) == 'allura/model/repo/Commit#foo', self.ci.index_id()
        assert self.ci.primary() is self.ci, self.ci.primary()


class TestCommit(_TestWithRepo):

    def setup_method(self, method):
        super().setup_method(method)
        self.ci, isnew = self._make_commit(
            'foo',
            a=dict(
                a=dict(
                    a='',
                    b='',),
                b=''))
        self.tree = self.ci.tree
        impl = M.RepositoryImplementation()
        impl._repo = self.repo
        self.repo._impl.shorthand_for_commit = impl.shorthand_for_commit
        self.repo._impl.url_for_commit = impl.url_for_commit

    def test_upsert(self):
        obj0, isnew0 = M.repository.Commit.upsert('foo')
        obj1, isnew1 = M.repository.Commit.upsert('foo')
        assert obj0 is obj1
        assert not isnew1
        u = M.User.by_username('test-admin')
        assert self.ci.author_url == u.url()
        assert self.ci.committer_url == u.url()
        assert self.ci.tree is self.tree
        assert self.ci.summary == 'summary'
        assert self.ci.shorthand_id() == '[foo]'
        assert self.ci.url() == '/p/test/test1/ci/foo/'

    def test_get_path(self):
        b = self.ci.get_path('a/a/a')
        assert isinstance(b, M.repository.Blob)
        x = self.ci.get_path('a/a')
        assert isinstance(x, M.repository.Tree)

    def _unique_blobs(self):
        def counter():
            counter.i += 1
            return counter.i
        counter.i = 0
        blobs = defaultdict(counter)
        return lambda blob: BytesIO(str(blobs[blob.path()]))

    def test_diffs_file_renames(self):
        def open_blob(blob):
            blobs = {
                'a': 'Leia',
                '/b/a/a': 'Darth Vader',
                '/b/a/b': 'Luke Skywalker',
                '/b/b': 'Death Star will destroy you',
                '/b/c': 'Luke Skywalker',  # moved from /b/a/b
                # moved from /b/b and modified
                '/b/a/z': 'Death Star will destroy you\nALL',
            }
            return BytesIO(blobs.get(blob.path(), ''))
        self.repo._impl.open_blob = open_blob

        self.repo._impl.commit = mock.Mock(return_value=self.ci)
        self.repo._impl.paged_diffs.return_value = {
            'added': ['a', 'a/a', 'a/a/a', 'a/a/b', 'a/b'],
            'changed': [],
            'copied': [],
            'renamed': [],
            'removed': [],
            'total': 5,
        }
        assert (self.ci.diffs.added ==
                ['a', 'a/a', 'a/a/a', 'a/a/b', 'a/b'])
        assert (self.ci.diffs.copied
                == self.ci.diffs.changed
                == self.ci.diffs.removed
                == [])

        ci, isnew = self._make_commit(
            'bar',
            b=dict(
                a=dict(
                    a='',
                    b='',),
                b=''))
        ci.parent_ids = ['foo']
        self._make_log(ci)
        self.repo._impl.paged_diffs.return_value = {
            'added': ['b', 'b/a', 'b/a/a', 'b/a/b', 'b/b'],
            'renamed': [],
            'copied': [],
            'changed': [],
            'removed': ['a', 'a/a', 'a/a/a', 'a/a/b', 'a/b'],
            'total': 10,
        }
        assert ci.diffs.added == ['b', 'b/a', 'b/a/a', 'b/a/b', 'b/b']
        assert ci.diffs.removed == ['a', 'a/a', 'a/a/a', 'a/a/b', 'a/b']
        assert (ci.diffs.copied
                == ci.diffs.changed
                == [])

        ci, isnew = self._make_commit(
            'baz',
            b=dict(
                a=dict(
                    z=''),
                c=''))
        ci.parent_ids = ['bar']
        self._make_log(ci)
        self.repo._impl.paged_diffs.return_value = {
            'added': ['b/c', 'b/a/z'],
            'removed': ['/b/a/b', 'b/b'],
            'changed': [],
            'copied': [
                {
                    'new': 'b/c',
                    'old': 'b/a/b',
                    'ratio': 1,
                    'diff': '',
                },
                {
                    'new': 'b/a/z',
                    'old': 'b/b',
                    'ratio': 1,
                    'diff': '',
                },
            ],
            'renamed': [],
            'total': 2
        }
        assert ci.diffs.added == ['b/a/z', 'b/c']
        assert ci.diffs.changed == []
        assert ci.diffs.removed == ['/b/a/b', 'b/b']
        # see mock for open_blob
        assert len(ci.diffs.copied) == 2
        assert ci.diffs.copied[1]['old'] == 'b/a/b'
        assert ci.diffs.copied[1]['new'] == 'b/c'
        assert ci.diffs.copied[1]['ratio'] == 1
        assert ci.diffs.copied[1]['diff'] == ''
        assert ci.diffs.copied[0]['old'] == 'b/b'
        assert ci.diffs.copied[0]['new'] == 'b/a/z'

    def test_context(self):
        self.ci.context()


class TestRename(unittest.TestCase):

    def setup_method(self, method):
        setup_basic_test()
        self.setup_with_tools()

    @with_svn
    def setup_with_tools(self):
        setup_global_objects()
        h.set_context('test', 'src', neighborhood='Projects')
        repo_dir = pkg_resources.resource_filename(
            'forgesvn', 'tests/data/')
        c.app.repo.name = 'testsvn-rename'
        c.app.repo.fs_path = repo_dir
        self.repo = c.app.repo
        self.repo.refresh()
        self.rev = self.repo.commit('HEAD')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_log_file_with_rename(self):
        entry = list(self.repo.log(path='/dir/b.txt', id_only=False, limit=1))[0]
        assert entry['id'] == 3
        assert entry['rename_details']['path'] == '/dir/a.txt'
        assert (
            entry['rename_details']['commit_url'] ==
            self.repo.url_for_commit(2))

    def test_check_changed_path(self):
        changed_path = {'copyfrom_path': '/test/path', 'path': '/test/path2'}
        result = self.repo._impl._check_changed_path(
            changed_path, '/test/path2/file.txt')
        assert {'path': '/test/path2/file.txt',
                'copyfrom_path': '/test/path/file.txt'} == result


class TestDirectRepoAccess:

    def setup_method(self, method):
        setup_basic_test()
        self.setup_with_tools()

    @with_svn
    def setup_with_tools(self):
        setup_global_objects()
        h.set_context('test', 'src', neighborhood='Projects')
        repo_dir = pkg_resources.resource_filename(
            'forgesvn', 'tests/data/')
        c.app.repo.name = 'testsvn'
        c.app.repo.fs_path = repo_dir
        self.repo = c.app.repo
        self.repo.refresh()
        self.rev = self.repo.commit('HEAD')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_paged_diffs(self):
        _id = self.repo._impl._oid(6)
        diffs = self.repo.commit(_id).diffs
        expected = {
            'added': ['/ЗРЯЧИЙ_ТА_ПОБАЧИТЬ'],
            'removed': [],
            'changed': [],
            'copied': [],
            'renamed': [],
            'total': 1,
        }
        assert diffs == expected

        _id = self.repo._impl._oid(2)
        diffs = self.repo.commit(_id).diffs
        expected = {
            'added': ['/a', '/a/b', '/a/b/c', '/a/b/c/hello.txt'],
            'removed': [],
            'changed': [],
            'renamed': [],
            'copied': [],
            'total': 4,
        }
        assert diffs == expected

        _id = self.repo._impl._oid(3)
        diffs = self.repo.commit(_id).diffs
        expected = {
            'added': [],
            'removed': [],
            'renamed': [],
            'changed': ['/README'],
            'copied': [],
            'total': 1,
        }
        assert diffs == expected

        _id = self.repo._impl._oid(4)
        diffs = self.repo.commit(_id).diffs
        expected = {
            'added': [],
            'removed': ['/a/b/c/hello.txt'],
            'changed': [],
            'renamed': [],
            'copied': [],
            'total': 1,
        }
        assert diffs == expected
