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

import sys
import re
import os
import shutil
import string
import logging
import subprocess
from subprocess import Popen, PIPE
from hashlib import sha1
from cStringIO import StringIO
from datetime import datetime
import tempfile
from shutil import rmtree

import tg
import pysvn
from paste.deploy.converters import asbool
from pymongo.errors import DuplicateKeyError
from pylons import tmpl_context as c, app_globals as g

from ming.base import Object
from ming.orm import Mapper, FieldProperty, session
from ming.utils import LazyProperty

from allura import model as M
from allura.lib import helpers as h
from allura.model.auth import User
from allura.model.repository import zipdir

log = logging.getLogger(__name__)

class Repository(M.Repository):
    tool_name='SVN'
    repo_id='svn'
    type_s='SVN Repository'
    class __mongometa__:
        name='svn-repository'
    branches = FieldProperty([dict(name=str,object_id=str)])
    _refresh_precompute = False

    @LazyProperty
    def _impl(self):
        return SVNImplementation(self)

    def clone_command(self, category, username=''):
        '''Return a string suitable for copy/paste that would clone this repo locally
           category is one of 'ro' (read-only), 'rw' (read/write), or 'https' (read/write via https)
        '''
        if not username and c.user not in (None, User.anonymous()):
            username = c.user.username
        tpl = string.Template(tg.config.get('scm.clone.%s.%s' % (category, self.tool)) or
                              tg.config.get('scm.clone.%s' % self.tool))
        return tpl.substitute(dict(username=username,
                                   source_url=self.clone_url(category, username)+c.app.config.options.get('checkout_url'),
                                   dest_path=self.suggested_clone_dest_path()))

    def compute_diffs(self): return

    def latest(self, branch=None):
        if self._impl is None: return None
        return self._impl.commit('HEAD')

    def tarball_filename(self, revision, path=None):
        fn = super(Repository, self).tarball_filename(revision, path)
        path = self._impl._path_to_root(path, revision)
        fn += ('-' + '-'.join(path.split('/'))) if path else ''
        return fn

    def rev_to_commit_id(self, rev):
        return self._impl.rev_parse(rev)


class SVNCalledProcessError(Exception):
    def __init__(self, cmd, returncode, stdout, stderr):
        self.cmd = cmd
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def __str__(self):
        return "Command: '%s' returned non-zero exit status %s\nSTDOUT: %s\nSTDERR: %s" % \
            (self.cmd, self.returncode, self.stdout, self.stderr)


def svn_path_exists(path, rev=None):
    svn = SVNLibWrapper(pysvn.Client())
    if rev:
        rev = pysvn.Revision(pysvn.opt_revision_kind.number, rev)
    else:
        rev = pysvn.Revision(pysvn.opt_revision_kind.head)
    try:
        svn.info2(path, revision=rev, recurse=False)
        return True
    except pysvn.ClientError:
        return False


class SVNLibWrapper(object):
    """Wrapper around pysvn, used for instrumentation."""
    def __init__(self, client):
        self.client = client

    def checkout(self, *args, **kw):
        return self.client.checkout(*args, **kw)

    def add(self, *args, **kw):
        return self.client.add(*args, **kw)

    def checkin(self, *args, **kw):
        return self.client.checkin(*args, **kw)

    def info2(self, *args, **kw):
        return self.client.info2(*args, **kw)

    def log(self, *args, **kw):
        return self.client.log(*args, **kw)

    def cat(self, *args, **kw):
        return self.client.cat(*args, **kw)

    def list(self, *args, **kw):
        return self.client.list(*args, **kw)

    def __getattr__(self, name):
        return getattr(self.client, name)


class SVNImplementation(M.RepositoryImplementation):
    post_receive_template = string.Template(
        '#!/bin/bash\n'
        '# The following is required for site integration, do not remove/modify.\n'
        '# Place user hook code in post-commit-user and it will be called from here.\n'
        'curl -s $url\n'
        '\n'
        'DIR="$$(dirname "$${BASH_SOURCE[0]}")"\n'
        'if [ -x $$DIR/post-commit-user ]; then'
        '  exec $$DIR/post-commit-user "$$@"\n'
        'fi')

    def __init__(self, repo):
        self._repo = repo

    @LazyProperty
    def _svn(self):
        return SVNLibWrapper(pysvn.Client())

    @LazyProperty
    def _url(self):
        return 'file://%s%s' % (self._repo.fs_path, self._repo.name)

    def shorthand_for_commit(self, oid):
        return '[r%d]' % self._revno(self.rev_parse(oid))

    def url_for_commit(self, commit, url_type=None):
        if hasattr(commit, '_id'):
            object_id = commit._id
        elif commit == self._repo.app.default_branch_name:
            object_id = commit
        else:
            object_id = self.rev_parse(commit)
        if ':' in object_id:
            object_id = str(self._revno(object_id))
        return os.path.join(self._repo.url(), object_id) + '/'

    def init(self, default_dirs=False, skip_special_files=False):
        fullname = self._setup_paths()
        log.info('svn init %s', fullname)
        if os.path.exists(fullname):
            shutil.rmtree(fullname)
        subprocess.call(['svnadmin', 'create', self._repo.name],
                                 stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,
                                 cwd=self._repo.fs_path)
        if not skip_special_files:
            self._setup_special_files()
        self._repo.set_status('ready')
        # make first commit with dir structure
        if default_dirs:
            tmp_working_dir = tempfile.mkdtemp(prefix='allura-svn-r1-',
                                               dir=tg.config.get('scm.svn.tmpdir', g.tmpdir))
            log.info('tmp dir = %s', tmp_working_dir)
            self._repo._impl._svn.checkout('file://'+fullname, tmp_working_dir)
            os.mkdir(tmp_working_dir+'/trunk')
            os.mkdir(tmp_working_dir+'/tags')
            os.mkdir(tmp_working_dir+'/branches')
            self._repo._impl._svn.add(tmp_working_dir+'/trunk')
            self._repo._impl._svn.add(tmp_working_dir+'/tags')
            self._repo._impl._svn.add(tmp_working_dir+'/branches')
            self._repo._impl._svn.checkin([tmp_working_dir+'/trunk',
                                           tmp_working_dir+'/tags',
                                           tmp_working_dir+'/branches'],
                                        'Initial commit')
            shutil.rmtree(tmp_working_dir)
            log.info('deleted %s', tmp_working_dir)

    def can_hotcopy(self, source_url):
        if not (asbool(tg.config.get('scm.svn.hotcopy', True)) and
                source_url.startswith('file://')):
            return False
        # check for svn version 1.7 or later
        stdout, stderr = self.check_call(['svn', '--version'])
        pattern = r'version (?P<maj>\d+)\.(?P<min>\d+)'
        m = re.search(pattern, stdout)
        return m and (int(m.group('maj')) * 10 + int(m.group('min'))) >= 17

    def check_call(self, cmd):
        p = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE)
        stdout, stderr = p.communicate(input='p\n')
        if p.returncode != 0:
            self._repo.set_status('ready')
            raise SVNCalledProcessError(cmd, p.returncode, stdout, stderr)
        return stdout, stderr

    def clone_from(self, source_url):
        '''Initialize a repo as a clone of another using svnsync'''
        self.init(skip_special_files=True)

        def set_hook(hook_name):
            fn = os.path.join(self._repo.fs_path, self._repo.name,
                              'hooks', hook_name)
            with open(fn, 'wb') as fp:
                fp.write('#!/bin/sh\n')
            os.chmod(fn, 0755)

        def clear_hook(hook_name):
            fn = os.path.join(self._repo.fs_path, self._repo.name,
                              'hooks', hook_name)
            os.remove(fn)

        self._repo.set_status('importing')
        log.info('Initialize %r as a clone of %s',
                 self._repo, source_url)

        if self.can_hotcopy(source_url):
            log.info('... cloning %s via hotcopy', source_url)
            # src repo is on the local filesystem - use hotcopy (faster)
            source_path, dest_path = source_url[7:], self._url[7:]
            fullname = os.path.join(self._repo.fs_path, self._repo.name)
            # hotcopy expects dest dir to not exist yet
            if os.path.exists(fullname):
                shutil.rmtree(fullname)
            self.check_call(['svnadmin', 'hotcopy', source_path, dest_path])
            # make sure new repo has a pre-revprop-change hook,
            # otherwise the sync will fail
            set_hook('pre-revprop-change')
            self.check_call(['svnsync', '--non-interactive', '--allow-non-empty',
              'initialize', self._url, source_url])
            clear_hook('pre-revprop-change')
        else:
            set_hook('pre-revprop-change')
            self.check_call(['svnsync', 'init', self._url, source_url])
            self.check_call(['svnsync', '--non-interactive', 'sync', self._url])
            clear_hook('pre-revprop-change')

        log.info('... %r cloned', self._repo)
        self.update_checkout_url()
        self._setup_special_files(source_url)

    def update_checkout_url(self):
        """Validate the current ``checkout_url`` against the on-disk repo,
        and change it if necessary.

        If ``checkout_url`` is valid and not '', no changes are made.
        If ``checkout_url`` is invalid or '':

            - Set it to 'trunk' if repo has a top-level trunk directory
            - Else, set it to ''

        """
        opts = self._repo.app.config.options
        if not svn_path_exists('file://{0}{1}/{2}'.format(self._repo.fs_path,
                self._repo.name, opts['checkout_url'])):
            opts['checkout_url'] = ''

        if (not opts['checkout_url'] and
                svn_path_exists('file://{0}{1}/trunk'.format(self._repo.fs_path,
                    self._repo.name))):
            opts['checkout_url'] = 'trunk'

    def commit(self, rev):
        oid = self.rev_parse(rev)
        result = M.repo.Commit.query.get(_id=oid)
        if result:
            result.set_context(self._repo)
        return result

    def rev_parse(self, rev):
        if rev in ('HEAD', None):
            return self._oid(self.head)
        elif isinstance(rev, int) or rev.isdigit():
            return self._oid(rev)
        else:
            return rev

    def all_commit_ids(self):
        """Return a list of commit ids, starting with the head (most recent
        commit) and ending with the root (first commit).
        """
        head_revno = self.head
        return map(self._oid, range(head_revno, 0, -1))

    def new_commits(self, all_commits=False):
        head_revno = self.head
        oids = [ self._oid(revno) for revno in range(1, head_revno+1) ]
        if all_commits:
            return oids
        # Find max commit id -- everything greater than that will be "unknown"
        prefix = self._oid('')
        q = M.repo.Commit.query.find(
            dict(
                type='commit',
                _id={'$gt':prefix},
                ),
            dict(_id=True)
            )
        seen_oids = set()
        for d in q.ming_cursor.cursor:
            oid = d['_id']
            if not oid.startswith(prefix): break
            seen_oids.add(oid)
        return [
            oid for oid in oids if oid not in seen_oids ]

    def refresh_commit_info(self, oid, seen_object_ids, lazy=True):
        from allura.model.repo import CommitDoc, DiffInfoDoc
        ci_doc = CommitDoc.m.get(_id=oid)
        if ci_doc and lazy: return False
        revno = self._revno(oid)
        rev = self._revision(oid)
        try:
            log_entry = self._svn.log(
                self._url,
                revision_start=rev,
                limit=1,
                discover_changed_paths=True)[0]
        except pysvn.ClientError:
            log.info('ClientError processing %r %r, treating as empty', oid, self._repo, exc_info=True)
            log_entry = Object(date='', message='', changed_paths=[])
        log_date = None
        if hasattr(log_entry, 'date'):
            log_date = datetime.utcfromtimestamp(log_entry.date)
        user = Object(
            name=h.really_unicode(log_entry.get('author', '--none--')),
            email='',
           date=log_date)
        args = dict(
            tree_id=None,
            committed=user,
            authored=user,
            message=h.really_unicode(log_entry.get("message", "--none--")),
            parent_ids=[],
            child_ids=[])
        if revno > 1:
            args['parent_ids'] = [ self._oid(revno-1) ]
        if ci_doc:
            ci_doc.update(**args)
            ci_doc.m.save()
        else:
            ci_doc = CommitDoc(dict(args, _id=oid))
            try:
                ci_doc.m.insert(safe=True)
            except DuplicateKeyError:
                if lazy: return False
        # Save diff info
        di = DiffInfoDoc.make(dict(_id=ci_doc._id, differences=[]))
        for path in log_entry.changed_paths:
            if path.action in ('A', 'M', 'R'):
                try:
                    rhs_info = self._svn.info2(
                        self._url + h.really_unicode(path.path),
                        revision=self._revision(ci_doc._id),
                        recurse=False)[0][1]
                    rhs_id = self._obj_oid(ci_doc._id, rhs_info)
                except pysvn.ClientError, e:
                    # pysvn will sometimes misreport deleted files (D) as
                    # something else (like A), causing info2() to raise a
                    # ClientError since the file doesn't exist in this
                    # revision. Set lrhs_id = None to treat like a deleted file
                    log.info('This error was handled gracefully and logged '
                             'for informational purposes only:\n' + str(e))
                    rhs_id = None
            else:
                rhs_id = None
            if ci_doc.parent_ids and path.action in ('D', 'M', 'R'):
                try:
                    lhs_info = self._svn.info2(
                        self._url + h.really_unicode(path.path),
                        revision=self._revision(ci_doc.parent_ids[0]),
                        recurse=False)[0][1]
                    lhs_id = self._obj_oid(ci_doc._id, lhs_info)
                except pysvn.ClientError, e:
                    # pysvn will sometimes report new files as 'M'odified,
                    # causing info2() to raise ClientError since the file
                    # doesn't exist in the parent revision. Set lhs_id = None
                    # to treat like a newly added file.
                    log.info('This error was handled gracefully and logged '
                             'for informational purposes only:\n' + str(e))
                    lhs_id = None
            else:
                lhs_id = None
            di.differences.append(dict(
                    name=h.really_unicode(path.path),
                    lhs_id=lhs_id,
                    rhs_id=rhs_id))
        di.m.save()
        return True

    def compute_tree_new(self, commit, tree_path='/'):
        from allura.model import repo as RM
        tree_path = '/' + tree_path.strip('/')  # always leading slash, never trailing
        tree_id = self._tree_oid(commit._id, tree_path)
        tree = RM.Tree.query.get(_id=tree_id)
        if tree:
            return tree_id
        log.debug('Computing tree for %s: %s',
                 self._revno(commit._id), tree_path)
        rev = self._revision(commit._id)
        try:
            infos = self._svn.info2(
                self._url + tree_path,
                revision=rev,
                depth=pysvn.depth.immediates)
        except pysvn.ClientError:
            log.exception('Error computing tree for: %s: %s(%s)',
                          self._repo, commit, tree_path)
            return None
        log.debug('Compute tree for %d paths', len(infos))
        tree_ids = []
        blob_ids = []
        lcd_entries = []
        for path, info in infos[1:]:
            if info.kind == pysvn.node_kind.dir:
                tree_ids.append(Object(
                        id=self._tree_oid(commit._id, path),
                        name=path))
            elif info.kind == pysvn.node_kind.file:
                blob_ids.append(Object(
                        id=self._tree_oid(commit._id, path),
                        name=path))
            else:
                assert False
            lcd_entries.append(dict(
                    name=path,
                    commit_id=self._oid(info.last_changed_rev.number),
                ))
        tree, is_new = RM.Tree.upsert(tree_id,
                tree_ids=tree_ids,
                blob_ids=blob_ids,
                other_ids=[],
            )
        if is_new:
            commit_id = self._oid(infos[0][1].last_changed_rev.number)
            path = tree_path.strip('/')
            RM.TreesDoc.m.update_partial(
                    {'_id': commit._id},
                    {'$addToSet': {'tree_ids': tree_id}},
                    upsert=True)
            RM.LastCommitDoc.m.update_partial(
                    {'commit_id': commit_id, 'path': path},
                    {'commit_id': commit_id, 'path': path, 'entries': lcd_entries},
                    upsert=True)
        return tree_id

    def _tree_oid(self, commit_id, path):
        data = 'tree\n%s\n%s' % (commit_id, h.really_unicode(path))
        return sha1(data.encode('utf-8')).hexdigest()

    def _blob_oid(self, commit_id, path):
        data = 'blob\n%s\n%s' % (commit_id, h.really_unicode(path))
        return sha1(data.encode('utf-8')).hexdigest()

    def _obj_oid(self, commit_id, info):
        path = info.URL[len(info.repos_root_URL):]
        if info.kind == pysvn.node_kind.dir:
            return self._tree_oid(commit_id, path)
        else:
            return self._blob_oid(commit_id, path)

    def log(self, revs=None, path=None, exclude=None, id_only=True, page_size=25, **kw):
        """
        Returns a generator that returns information about commits reachable
        by revs.

        revs can be None or a list or tuple of identifiers, each of which
        can be anything parsable by self.commit().  If revs is None, the
        default head will be used.

        If path is not None, only commits which modify files under path
        will be included.

        Exclude can be None or a list or tuple of identifiers, each of which
        can be anything parsable by self.commit().  If not None, then any
        revisions reachable by any of the revisions in exclude will not be
        included.

        If id_only is True, returns only the commit ID, otherwise it returns
        detailed information about each commit.

        Since pysvn doesn't have a generator version of log, this tries to
        balance pulling too much data from SVN with calling SVN too many
        times by pulling in pages of page_size at a time.
        """
        if revs is None:
            revno = self.head
        else:
            revno = max([self._revno(self.rev_parse(r)) for r in revs])
        if exclude is None:
            exclude = 0
        else:
            exclude = max([self._revno(self.rev_parse(r)) for r in exclude])
        if path is None:
            url = self._url
        else:
            url = '/'.join([self._url, path.strip('/')])
        while revno > exclude:
            rev = pysvn.Revision(pysvn.opt_revision_kind.number, revno)
            try:
                logs = self._svn.log(url, revision_start=rev, peg_revision=rev, limit=page_size,
                    discover_changed_paths=True)
            except pysvn.ClientError as e:
                if 'Unable to connect' in e.message:
                    raise  # repo error
                return  # no (more) history for this path
            for ci in logs:

                if ci.revision.number <= exclude:
                    return
                if id_only:
                    yield ci.revision.number
                else:
                    yield self._map_log(ci, url, path)
            if len(logs) < page_size:
                return  # we didn't get a full page, don't bother calling SVN again
            revno = ci.revision.number - 1

    def _check_changed_path(self, changed_path, path):
        if (changed_path['copyfrom_path'] and
                    changed_path['path'] and
                    path and
                    (len(changed_path['path']) < len(path)) and
                    path.startswith(changed_path['path'])):
                changed_path['copyfrom_path'] = changed_path['copyfrom_path'] + path[len(changed_path['path']):]
                changed_path['path'] = path
        return changed_path

    def _map_log(self, ci, url, path=None):
        revno = ci.revision.number
        rev = pysvn.Revision(pysvn.opt_revision_kind.number, revno)
        try:
            size = int(self._svn.list(url, revision=rev, peg_revision=rev)[0][0].size)
        except pysvn.ClientError:
            size = None
        rename_details = {}
        changed_paths = ci.get('changed_paths', [])
        for changed_path in changed_paths:
            changed_path = self._check_changed_path(changed_path, path)
            if changed_path['copyfrom_path'] and changed_path['path'] == path and changed_path['action'] == 'A':
                rename_details['path'] = changed_path['copyfrom_path']
                rename_details['commit_url'] = self._repo.url_for_commit(
                    changed_path['copyfrom_revision'].number
                )
                break
        return {
                'id': revno,
                'message': h.really_unicode(ci.get('message', '--none--')),
                'authored': {
                        'name': h.really_unicode(ci.get('author', '--none--')),
                        'email': '',
                        'date': datetime.utcfromtimestamp(ci.date),
                    },
                'committed': {
                        'name': h.really_unicode(ci.get('author', '--none--')),
                        'email': '',
                        'date': datetime.utcfromtimestamp(ci.date),
                    },
                'refs': ['HEAD'] if revno == self.head else [],
                'parents': [revno-1] if revno > 1 else [],
                'size': size,
                'rename_details': rename_details,
            }

    def open_blob(self, blob):
        data = self._svn.cat(
            self._url + blob.path(),
            revision=self._revision(blob.commit._id))
        return StringIO(data)

    def blob_size(self, blob):
        try:
            rev = self._revision(blob.commit._id)
            data = self._svn.list(
                   self._url + blob.path(),
                   revision=rev,
                   peg_revision=rev,
                   dirent_fields=pysvn.SVN_DIRENT_SIZE)
        except pysvn.ClientError:
            log.info('ClientError getting filesize %r %r, returning 0', blob.path(), self._repo, exc_info=True)
            return 0

        try:
            size = data[0][0]['size']
        except (IndexError, KeyError):
            log.info('Error getting filesize: bad data from svn client %r %r, returning 0', blob.path(), self._repo, exc_info=True)
            size = 0

        return size

    def _setup_hooks(self, source_path=None):
        'Set up the post-commit and pre-revprop-change hooks'
        # setup a post-commit hook to notify Allura of changes to the repo
        # the hook should also call the user-defined post-commit-user hook
        text = self.post_receive_template.substitute(
            url=tg.config.get('base_url', 'http://localhost:8080')
            + '/auth/refresh_repo' + self._repo.url())
        fn = os.path.join(self._repo.fs_path, self._repo.name, 'hooks', 'post-commit')
        with open(fn, 'wb') as fp:
            fp.write(text)
        os.chmod(fn, 0755)

    def _revno(self, oid):
        return int(oid.split(':')[1])

    def _revision(self, oid):
        return pysvn.Revision(
            pysvn.opt_revision_kind.number,
            self._revno(oid))

    def _oid(self, revno):
        return '%s:%s' % (self._repo._id, revno)

    def last_commit_ids(self, commit, paths):
        '''
        Return a mapping {path: commit_id} of the _id of the last
        commit to touch each path, starting from the given commit.

        Since SVN Diffs are computed on-demand, we can't walk the
        commit tree to find these.  However, we can ask SVN for it
        with a single call, so it shouldn't be too expensive.

        NB: This assumes that all paths are direct children of a
        single common parent path (i.e., you are only asking for
        a subset of the nodes of a single tree, one level deep).
        '''
        if len(paths) == 1:
            tree_path = '/' + os.path.dirname(paths[0].strip('/'))
        else:
            tree_path = '/' + os.path.commonprefix(paths).strip('/')  # always leading slash, never trailing
        paths = [path.strip('/') for path in paths]
        rev = self._revision(commit._id)
        try:
            infos = self._svn.info2(
                self._url + tree_path,
                revision=rev,
                depth=pysvn.depth.immediates)
        except pysvn.ClientError:
            log.exception('Error computing tree for: %s: %s(%s)',
                          self._repo, commit, tree_path)
            return None
        entries = {}
        for path, info in infos[1:]:
            path = os.path.join(tree_path, path).strip('/')
            if path in paths:
                entries[path] = self._oid(info.last_changed_rev.number)
        return entries

    def get_changes(self, oid):
        rev = self._revision(oid)
        try:
            log_entry = self._svn.log(
                self._url,
                revision_start=rev,
                limit=1,
                discover_changed_paths=True)[0]
        except pysvn.ClientError:
            log.info('ClientError processing %r %r, treating as empty', oid, self._repo, exc_info=True)
            log_entry = Object(date='', message='', changed_paths=[])
        return [p.path for p in log_entry.changed_paths]

    def _path_to_root(self, path, rev=None):
        '''Return tag/branch/trunk root for given path inside svn repo'''
        if path:
            path = path.strip('/').split('/')
            idx = None
            if 'tags' in path:
                idx = path.index('tags')
            elif 'branches' in path:
                idx = path.index('branches')
            if idx is not None and idx < len(path) - 1:  # e.g. path/tags/tag-1.0/...
                return '/'.join(path[:idx + 2])  # path/tags/tag-1.0
            if 'trunk' in path:
                idx = path.index('trunk')
                return '/'.join(path[:idx + 1])  # path/trunk
        # no tag/brach/trunk in path
        trunk_exists = svn_path_exists(
            'file://%s%s/%s' % (self._repo.fs_path, self._repo.name, 'trunk'), rev)
        if trunk_exists:
            return 'trunk'
        return ''

    def tarball(self, commit, path=None):
        path = self._path_to_root(path, commit)
        if not os.path.exists(self._repo.tarball_path):
            os.makedirs(self._repo.tarball_path)
        archive_name = self._repo.tarball_filename(commit, path)
        dest = os.path.join(self._repo.tarball_path, archive_name)
        filename = os.path.join(self._repo.tarball_path, '%s%s' % (archive_name, '.zip'))
        tmpfilename = os.path.join(self._repo.tarball_path, '%s%s' % (archive_name, '.tmp'))
        rmtree(dest, ignore_errors=True)
        path = os.path.join(self._url, path)
        try:
            # need to set system locale to handle all symbols in filename
            import locale
            locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
            self._svn.export(path,
                             dest,
                             revision=pysvn.Revision(pysvn.opt_revision_kind.number, commit),
                             ignore_externals=True)
            zipdir(dest, tmpfilename)
            os.rename(tmpfilename, filename)
        finally:
            rmtree(dest, ignore_errors=True)
            if os.path.exists(tmpfilename):
                os.remove(tmpfilename)

    def is_empty(self):
        return self.head == 0

    def is_file(self, path, rev=None):
        url = '/'.join([self._url, path.strip('/')])
        rev = pysvn.Revision(pysvn.opt_revision_kind.number, self._revno(self.rev_parse(rev)))
        try:
            info = self._svn.list(url, revision=rev, peg_revision=rev, dirent_fields=pysvn.SVN_DIRENT_KIND)[0][0]
            return info.kind == pysvn.node_kind.file
        except pysvn.ClientError:
            return False

    def symbolics_for_commit(self, commit):
        return [], []

    @LazyProperty
    def head(self):
        try:
            return int(self._svn.revpropget('revision', url=self._url)[0].number)
        except pysvn.ClientError as e:
            if str(e).startswith("Unable to connect") or \
                    str(e).startswith("Unable to open"):
                return 0
            else:
                raise

    @LazyProperty
    def heads(self):
        return [Object(name=None, object_id=self._oid(self.head))]

    @LazyProperty
    def branches(self):
        return []

    @LazyProperty
    def tags(self):
        return []


Mapper.compile_all()
