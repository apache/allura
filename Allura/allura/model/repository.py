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
import os
import stat
import errno
import mimetypes
import logging
import string
import re
from subprocess import Popen, PIPE
from difflib import SequenceMatcher
from hashlib import sha1
from datetime import datetime
from time import time
from collections import defaultdict
from itertools import izip
from urlparse import urljoin
from urllib import quote
from threading import Thread
from Queue import Queue

import tg
from paste.deploy.converters import asbool, asint
from pylons import tmpl_context as c
from pylons import app_globals as g
import pymongo
import pymongo.errors

from ming import schema as S
from ming.utils import LazyProperty
from ming.orm import FieldProperty, session, Mapper
from ming.orm.declarative import MappedClass

from allura.lib import helpers as h
from allura.lib import utils

from .artifact import Artifact, VersionedArtifact, Feed
from .auth import User
from .session import repository_orm_session, project_orm_session
from .notification import Notification
from .repo_refresh import refresh_repo, unknown_commit_ids as unknown_commit_ids_repo
from .repo import CommitRunDoc, QSIZE
from .timeline import ActivityObject
from .monq_model import MonQTask

log = logging.getLogger(__name__)
config = utils.ConfigProxy(
    common_suffix='forgemail.domain',
    common_prefix='forgemail.url')

README_RE = re.compile('^README(\.[^.]*)?$', re.IGNORECASE)
VIEWABLE_EXTENSIONS = ['.php','.py','.js','.java','.html','.htm','.yaml','.sh',
    '.rb','.phtml','.txt','.bat','.ps1','.xhtml','.css','.cfm','.jsp','.jspx',
    '.pl','.php4','.php3','.rhtml','.svg','.markdown','.json','.ini','.tcl','.vbs','.xsl']

class RepositoryImplementation(object):

    # Repository-specific code
    def init(self): # pragma no cover
        raise NotImplementedError, 'init'

    def clone_from(self, source_url): # pragma no cover
        raise NotImplementedError, 'clone_from'

    def commit(self, revision): # pragma no cover
        raise NotImplementedError, 'commit'

    def all_commit_ids(self): # pragma no cover
        raise NotImplementedError, 'all_commit_ids'

    def new_commits(self, all_commits=False): # pragma no cover
        '''Return a list of native commits in topological order (heads first).

        "commit" is a repo-native object, NOT a Commit object.
        If all_commits is False, only return commits not already indexed.
        '''
        raise NotImplementedError, 'new_commits'

    def commit_parents(self, commit): # pragma no cover
        '''Return a list of native commits for the parents of the given (native)
        commit'''
        raise NotImplementedError, 'commit_parents'

    def refresh_commit_info(self, oid, lazy=True): # pragma no cover
        '''Refresh the data in the commit with id oid'''
        raise NotImplementedError, 'refresh_commit_info'

    def _setup_hooks(self, source_path=None): # pragma no cover
        '''Install a hook in the repository that will ping the refresh url for
        the repo.  Optionally provide a path from which to copy existing hooks.'''
        raise NotImplementedError, '_setup_hooks'

    def log(self, revs=None, path=None, exclude=None, id_only=True, **kw): # pragma no cover
        """
        Returns a generator that returns information about commits reachable
        by revs.

        revs can be None or a list or tuple of identifiers, each of which
        can be anything parsable by self.commit().  If revs is None, the
        default branch head will be used.

        If path is not None, only commits which modify files under path
        will be included.

        Exclude can be None or a list or tuple of identifiers, each of which
        can be anything parsable by self.commit().  If not None, then any
        revisions reachable by any of the revisions in exclude will not be
        included.

        If id_only is True, returns only the commit ID (which can be faster),
        otherwise it returns detailed information about each commit.
        """
        raise NotImplementedError, 'log'

    def compute_tree_new(self, commit, path='/'): # pragma no cover
        '''Used in hg and svn to compute a git-like-tree lazily with the new models'''
        raise NotImplementedError, 'compute_tree'

    def open_blob(self, blob): # pragma no cover
        '''Return a file-like object that contains the contents of the blob'''
        raise NotImplementedError, 'open_blob'

    def blob_size(self, blob):
        '''Return a blob size in bytes'''
        raise NotImplementedError, 'blob_size'

    def tarball(self, revision, path=None):
        '''Create a tarball for the revision'''
        raise NotImplementedError, 'tarball'

    def is_empty(self):
        '''Determine if the repository is empty by checking the filesystem'''
        raise NotImplementedError, 'is_empty'

    def is_file(self, path, rev=None):
        '''Determine if the repository is a file by checking the filesystem'''
        raise NotImplementedError, 'is_file'

    @classmethod
    def shorthand_for_commit(cls, oid):
        return '[%s]' % oid[:6]

    def symbolics_for_commit(self, commit):
        '''Return symbolic branch and tag names for a commit.'''
        raise NotImplementedError, 'symbolics_for_commit'

    def url_for_commit(self, commit, url_type='ci'):
        'return an URL, given either a commit or object id'
        if isinstance(commit, basestring):
            object_id = commit
        else:
            object_id = commit._id

        if '/' in object_id:
            object_id = os.path.join(object_id, self._repo.app.END_OF_REF_ESCAPE)

        return os.path.join(self._repo.url(), url_type, object_id) + '/'

    def _setup_paths(self, create_repo_dir=True):
        '''
        Ensure that the base directory in which the repo lives exists.
        If create_repo_dir is True, also ensure that the directory
        of the repo itself exists.
        '''
        if not self._repo.fs_path.endswith('/'): self._repo.fs_path += '/'
        fullname = self._repo.fs_path + self._repo.name
        # make the base dir for repo, regardless
        if not os.path.exists(self._repo.fs_path):
            os.makedirs(self._repo.fs_path)
        if create_repo_dir and not os.path.exists(fullname):
            os.mkdir(fullname)
        return fullname

    def _setup_special_files(self, source_path=None):
        magic_file = os.path.join(self._repo.fs_path, self._repo.name, '.SOURCEFORGE-REPOSITORY')
        with open(magic_file, 'w') as f:
            f.write(self._repo.repo_id)
        os.chmod(magic_file, stat.S_IRUSR|stat.S_IRGRP|stat.S_IROTH)
        self._setup_hooks(source_path)

    @property
    def head(self):
        raise NotImplementedError, 'head'

    @property
    def heads(self):
        raise NotImplementedError, 'heads'

    @property
    def branches(self):
        raise NotImplementedError, 'branches'

    @property
    def tags(self):
        raise NotImplementedError, 'tags'

    def last_commit_ids(self, commit, paths):
        '''
        Return a mapping {path: commit_id} of the _id of the last
        commit to touch each path, starting from the given commit.

        Chunks the set of paths based on lcd_thread_chunk_size and
        runs each chunk (if more than one) in a separate thread.

        Each thread will call :meth:`_get_last_commit` to get the
        commit ID and list of changed files for the last commit
        to touch any file in a given chunk.
        '''
        if not paths:
            return {}
        timeout = float(tg.config.get('lcd_timeout', 60))
        start_time = time()
        paths = list(set(paths))  # remove dupes
        result = {}  # will be appended to from each thread
        chunks = Queue()
        lcd_chunk_size = asint(tg.config.get('lcd_thread_chunk_size', 10))
        num_threads = 0
        for s in range(0, len(paths), lcd_chunk_size):
            chunks.put(paths[s:s+lcd_chunk_size])
            num_threads += 1
        def get_ids():
            paths = set(chunks.get())
            try:
                commit_id = commit._id
                while paths and commit_id:
                    if time() - start_time >= timeout:
                        log.error('last_commit_ids timeout for %s on %s', commit._id, ', '.join(paths))
                        break
                    commit_id, changes = self._get_last_commit(commit._id, paths)
                    if commit_id is None:
                        break
                    changed = prefix_paths_union(paths, changes)
                    for path in changed:
                        result[path] = commit_id
                    paths -= changed
            except Exception as e:
                log.exception('Error in SCM thread: %s', e)
            finally:
                chunks.task_done()
        if num_threads == 1:
            get_ids()
        else:
            for i in range(num_threads):
                t = Thread(target=get_ids)
                t.start()
            # reimplement chunks.join() but with a timeout
            # see: http://bugs.python.org/issue9634
            # (giving threads a bit of extra cleanup time in case they timeout)
            chunks.all_tasks_done.acquire()
            try:
                endtime = time() + timeout + 0.5
                while chunks.unfinished_tasks and endtime > time():
                    chunks.all_tasks_done.wait(endtime - time())
            finally:
                chunks.all_tasks_done.release()
        return result

    def _get_last_commit(self, commit_id, paths):
        """
        For a given commit ID and set of paths / files,
        use the SCM to determine the last commit to touch
        any of the given paths / files.

        Should return a tuple containing the ID of the
        commit and the list of all files changed in the commit.
        """
        raise NotImplementedError('_get_last_commit')

    def get_changes(self, commit_id):
        """
        Return the list of files changed by a given commit.
        """
        raise NotImplemented('get_changes')

class Repository(Artifact, ActivityObject):
    BATCH_SIZE=100
    class __mongometa__:
        name='generic-repository'
        indexes = ['upstream_repo.name']
    _impl = None
    repo_id='repo'
    type_s='Repository'
    _refresh_precompute = True

    name=FieldProperty(str)
    tool=FieldProperty(str)
    fs_path=FieldProperty(str)
    url_path=FieldProperty(str)
    status=FieldProperty(str)
    email_address=''
    additional_viewable_extensions=FieldProperty(str)
    heads = FieldProperty(S.Deprecated)
    branches = FieldProperty(S.Deprecated)
    repo_tags = FieldProperty(S.Deprecated)
    upstream_repo = FieldProperty(dict(name=str,url=str))
    default_branch_name = FieldProperty(str)

    def __init__(self, **kw):
        if 'name' in kw and 'tool' in kw:
            if kw.get('fs_path') is None:
                kw['fs_path'] = self.default_fs_path(c.project, kw['tool'])
            if kw.get('url_path') is None:
                kw['url_path'] = self.default_url_path(c.project, kw['tool'])
        super(Repository, self).__init__(**kw)

    @property
    def activity_name(self):
        return 'repo %s' % self.name

    @classmethod
    def default_fs_path(cls, project, tool):
        repos_root = tg.config.get('scm.repos.root', '/')
        return os.path.join(repos_root, tool, project.url()[1:])

    @classmethod
    def default_url_path(cls, project, tool):
        return project.url()

    @property
    def tarball_path(self):
        return os.path.join(tg.config.get('scm.repos.tarball.root', '/'),
                            self.tool,
                            self.project.shortname[:1],
                            self.project.shortname[:2],
                            self.project.shortname,
                            self.name)

    def tarball_filename(self, revision, path=None):
        shortname = c.project.shortname.replace('/', '-')
        mount_point = c.app.config.options.mount_point
        filename = '%s-%s-%s' % (shortname, mount_point, revision)
        return filename

    def tarball_url(self, revision, path=None):
        filename = '%s%s' % (self.tarball_filename(revision, path), '.zip')
        r = os.path.join(self.tool,
                         self.project.shortname[:1],
                         self.project.shortname[:2],
                         self.project.shortname,
                         self.name,
                         filename)
        return urljoin(tg.config.get('scm.repos.tarball.url_prefix', '/'), r)

    def get_tarball_status(self, revision, path=None):
        pathname = os.path.join(self.tarball_path, self.tarball_filename(revision, path))
        filename = '%s%s' % (pathname, '.zip')
        if os.path.isfile(filename):
            return 'complete'

        # file doesn't exist, check for busy task
        task = MonQTask.query.get(**{
            'task_name': 'allura.tasks.repo_tasks.tarball',
            'args': [revision, path or ''],
            'state': {'$in': ['busy', 'ready']},
            })

        return task.state if task else None


    def __repr__(self): # pragma no cover
        return '<%s %s>' % (
            self.__class__.__name__,
            self.full_fs_path)

    # Proxy to _impl
    def init(self):
        return self._impl.init()
    def commit(self, rev):
        return self._impl.commit(rev)
    def all_commit_ids(self):
        return self._impl.all_commit_ids()
    def refresh_commit_info(self, oid, seen, lazy=True):
        return self._impl.refresh_commit_info(oid, seen, lazy)
    def open_blob(self, blob):
        return self._impl.open_blob(blob)
    def blob_size(self, blob):
        return self._impl.blob_size(blob)
    def shorthand_for_commit(self, oid):
        return self._impl.shorthand_for_commit(oid)
    def symbolics_for_commit(self, commit):
        return self._impl.symbolics_for_commit(commit)
    def url_for_commit(self, commit, url_type='ci'):
        return self._impl.url_for_commit(commit, url_type)
    def compute_tree_new(self, commit, path='/'):
        return self._impl.compute_tree_new(commit, path)
    def last_commit_ids(self, commit, paths):
        return self._impl.last_commit_ids(commit, paths)
    def get_changes(self, commit_id):
        return self._impl.get_changes(commit_id)
    def is_empty(self):
        return self._impl.is_empty()
    def is_file(self, path, rev=None):
        return self._impl.is_file(path, rev)
    def get_heads(self):
        """
        Return list of heads for the repo.

        It's get_heads() instead of a heads (lazy) property because it would
        conflict with the now deprecated heads field.  Eventually, we should
        try to remove the deprecated fields and clean this up.
        """
        return self._impl.heads
    def get_branches(self):
        """
        Return list of branches for the repo.

        It's get_branches() instead of a branches (lazy) property because it
        would conflict with the now deprecated branches field.  Eventually, we
        should try to remove the deprecated fields and clean this up.
        """
        return self._impl.branches
    def get_tags(self):
        """
        Return list of tags for the repo.

        It's get_tags() instead of a tags (lazy) property because it
        would conflict with the now deprecated tags field.  Eventually, we
        should try to remove the deprecated fields and clean this up.
        """
        return self._impl.tags
    @property
    def head(self):
        return self._impl.head
    def set_default_branch(self, name):
        return self._impl.set_default_branch(name)

    def _log(self, rev, skip, limit):
        head = self.commit(rev)
        if head is None: return
        for _id in self.commitlog([head._id], skip, limit):
            ci = head.query.get(_id=_id)
            ci.set_context(self)
            yield ci

    def init_as_clone(self, source_path, source_name, source_url):
        self.upstream_repo.name = source_name
        self.upstream_repo.url = source_url
        session(self).flush(self)
        source = source_path if source_path else source_url
        self._impl.clone_from(source)
        log.info('... %r cloned', self)
        g.post_event('repo_cloned', source_url, source_path)
        self.refresh(notify=False, new_clone=True)

    def log(self, revs=None, path=None, exclude=None, id_only=True, **kw):
        """
        Returns a generator that returns information about commits reachable
        by revs which modify path.

        revs can either be a single revision identifier or a list or tuple
        of identifiers, each of which can be anything parsable by self.commit().
        If revs is None, the default branch head will be used.

        If path is not None, then only commits which change files under path
        will be included.

        Exclude can be None, a single revision identifier, or a list or tuple of
        identifiers, each of which can be anything parsable by self.commit().
        If not None, then any revisions reachable by any of the revisions in
        exclude will not be included.

        If id_only is True, returns only the commit ID (which can be faster),
        otherwise it returns detailed information about each commit.
        """
        if revs is not None and not isinstance(revs, (list, tuple)):
            revs = [revs]
        if exclude is not None and not isinstance(exclude, (list, tuple)):
            exclude = [exclude]
        return self._impl.log(revs, path, exclude=exclude, id_only=id_only, **kw)

    def latest(self, branch=None):
        if self._impl is None:
            return None
        if branch is None:
            branch = self.app.default_branch_name
        try:
            return self.commit(branch)
        except: # pragma no cover
            log.exception('Cannot get latest commit for a branch', branch)
            return None

    def url(self):
        return self.app_config.url()

    def shorthand_id(self):
        return self.name

    @property
    def email_address(self):
        domain = '.'.join(reversed(self.app.url[1:-1].split('/'))).replace('_', '-')
        return u'noreply@%s%s' % (domain, config.common_suffix)

    def index(self):
        result = Artifact.index(self)
        result.update(
            name_s=self.name,
            type_s=self.type_s,
            title='Repository %s %s' % (self.project.name, self.name))
        return result

    @property
    def full_fs_path(self):
        return os.path.join(self.fs_path, self.name)

    def suggested_clone_dest_path(self):
        return '%s-%s' % (c.project.shortname.replace('/', '-'), self.name)

    def clone_url(self, category, username=''):
        '''Return a URL string suitable for copy/paste that describes _this_ repo,
           e.g., for use in a clone/checkout command
        '''
        tpl = string.Template(tg.config.get('scm.host.%s.%s' % (category, self.tool)))
        return tpl.substitute(dict(username=username, path=self.url_path+self.name))

    def clone_command(self, category, username=''):
        '''Return a string suitable for copy/paste that would clone this repo locally
           category is one of 'ro' (read-only), 'rw' (read/write), or 'https' (read/write via https)
        '''
        if not username and c.user not in (None, User.anonymous()):
            username = c.user.username
        tpl = string.Template(tg.config.get('scm.clone.%s.%s' % (category, self.tool)) or
                              tg.config.get('scm.clone.%s' % self.tool))
        return tpl.substitute(dict(username=username,
                                   source_url=self.clone_url(category, username),
                                   dest_path=self.suggested_clone_dest_path()))

    def merge_requests_by_statuses(self, *statuses):
        return MergeRequest.query.find(dict(
                app_config_id=self.app.config._id,
                status={'$in':statuses})).sort(
            'request_number')

    @LazyProperty
    def _additional_viewable_extensions(self):
        ext_list = self.additional_viewable_extensions or ''
        ext_list = [ext.strip() for ext in ext_list.split(',') if ext]
        ext_list += [ '.ini', '.gitignore', '.svnignore', 'README' ]
        return ext_list

    def guess_type(self, name):
        '''Guess the mime type and encoding of a given filename'''
        content_type, encoding = mimetypes.guess_type(name)
        if content_type is None or not content_type.startswith('text/'):
            fn, ext = os.path.splitext(name)
            ext = ext or fn
            if ext in self._additional_viewable_extensions:
                content_type, encoding = 'text/plain', None
            if content_type is None:
                content_type, encoding = 'application/octet-stream', None
        return content_type, encoding

    def unknown_commit_ids(self):
        return unknown_commit_ids_repo(self.all_commit_ids())

    def refresh(self, all_commits=False, notify=True, new_clone=False):
        '''Find any new commits in the repository and update'''
        try:
            log.info('... %r analyzing', self)
            self.set_status('analyzing')
            refresh_repo(self, all_commits, notify, new_clone)
        finally:
            log.info('... %s ready', self)
            self.set_status('ready')

    def push_upstream_context(self):
        project, rest=h.find_project(self.upstream_repo.name)
        with h.push_context(project._id):
            app = project.app_instance(rest[0])
        return h.push_context(project._id, app_config_id=app.config._id)

    def pending_upstream_merges(self):
        q = {
            'downstream.project_id':self.project_id,
            'downstream.mount_point':self.app.config.options.mount_point,
            'status':'open'}
        with self.push_upstream_context():
            return MergeRequest.query.find(q).count()

    @property
    def forks(self):
        all_forks = self.query.find({'upstream_repo.name': self.url()}).all()
        return filter(lambda fork: fork.app_config is not None, all_forks)

    def tarball(self, revision, path=None):
        if path:
            path = path.strip('/')
        self._impl.tarball(revision, path)

    def rev_to_commit_id(self, rev):
        raise NotImplementedError, 'rev_to_commit_id'

    def set_status(self, status):
        '''
        Update (and flush) the repo status indicator.

        Updates to the repo status (or any Repository field) are considered
        project updates (because Repositories are Artifacts; see
        `Artifact.__metaclass__.before_save`) and thus change `last_updated`
        on `c.project`, which causes `c.project` to be flushed.

        Because repo status changes can come at the end or middle of a long
        operation, `c.project` can be quite stale, so this flushes and reloads
        `c.project`.
        '''
        from allura.model import Project
        project_session = session(c.project)
        if project_session:
            session(c.project).flush(c.project)
            session(c.project).expunge(c.project)
            c.project = Project.query.get(_id=c.project._id)
        self.status = status
        session(self).flush(self)

class MergeRequest(VersionedArtifact, ActivityObject):
    statuses=['open', 'merged', 'rejected']
    class __mongometa__:
        name='merge-request'
        indexes=['commit_id']
        unique_indexes=[('app_config_id', 'request_number')]
    type_s='MergeRequest'

    request_number=FieldProperty(int)
    status=FieldProperty(str, if_missing='open')
    downstream=FieldProperty(dict(
            project_id=S.ObjectId,
            mount_point=str,
            commit_id=str))
    source_branch=FieldProperty(str,if_missing='')
    target_branch=FieldProperty(str)
    creator_id=FieldProperty(S.ObjectId, if_missing=lambda:c.user._id)
    created=FieldProperty(datetime, if_missing=datetime.utcnow)
    summary=FieldProperty(str)
    description=FieldProperty(str)

    @property
    def activity_name(self):
        return 'merge request #%s' % self.request_number

    @LazyProperty
    def creator(self):
        from allura import model as M
        return M.User.query.get(_id=self.creator_id)

    @LazyProperty
    def creator_name(self):
        return self.creator.get_pref('display_name') or self.creator.username

    @LazyProperty
    def creator_url(self):
        return self.creator.url()

    @LazyProperty
    def downstream_url(self):
        with self.push_downstream_context():
            return c.app.url

    @LazyProperty
    def downstream_repo_url(self):
        with self.push_downstream_context():
            return c.app.repo.clone_url(
                category='ro',
                username=c.user.username)

    def push_downstream_context(self):
        return h.push_context(self.downstream.project_id, self.downstream.mount_point)

    @LazyProperty
    def commits(self):
        return self._commits()

    def _commits(self):
        with self.push_downstream_context():
            return list(c.app.repo.log(
                self.downstream.commit_id,
                exclude=self.app.repo.head,
                id_only=False))

    @classmethod
    def upsert(cls, **kw):
        num = cls.query.find(dict(
                app_config_id=c.app.config._id)).count()+1
        while True:
            try:
                r = cls(request_number=num, **kw)
                session(r).flush(r)
                return r
            except pymongo.errors.DuplicateKeyError: # pragma no cover
                session(r).expunge(r)
                num += 1

    def url(self):
        return self.app.url + 'merge-requests/%s/' % self.request_number

    def index(self):
        result = Artifact.index(self)
        result.update(
            name_s='Merge Request #%d' % self.request_number,
            type_s=self.type_s,
            title='Merge Request #%d of %s:%s' % (
                self.request_number, self.project.name, self.app.repo.name))
        return result


class GitLikeTree(object):
    '''
    A tree node similar to that which is used in git

    :var dict blobs: files at this level of the tree.  name => oid
    :var dict trees: subtrees (child dirs).  name => GitLikeTree
    '''

    def __init__(self):
        self.blobs = {}  # blobs[name] = oid
        self.trees = defaultdict(GitLikeTree) #trees[name] = GitLikeTree()
        self._hex = None

    def get_tree(self, path):
        if path.startswith('/'): path = path[1:]
        if not path: return self
        cur = self
        for part in path.split('/'):
            cur = cur.trees[part]
        return cur

    def get_blob(self, path):
        if path.startswith('/'): path = path[1:]
        path_parts = path.split('/')
        dirpath, last = path_parts[:-1], path_parts[-1]
        cur = self
        for part in dirpath:
            cur = cur.trees[part]
        return cur.blobs[last]

    def set_blob(self, path, oid):
        if path.startswith('/'): path = path[1:]
        path_parts = path.split('/')
        dirpath, filename = path_parts[:-1], path_parts[-1]
        cur = self
        for part in dirpath:
            cur = cur.trees[part]
        cur.blobs[filename] = oid

    def hex(self):
        '''Compute a recursive sha1 hash on the tree'''
        # dependent on __repr__ below
        if self._hex is None:
            sha_obj = sha1('tree\n' + repr(self))
            self._hex = sha_obj.hexdigest()
        return self._hex

    def __repr__(self):
        # this can't change, is used in hex() above
        lines = ['t %s %s' % (t.hex(), name)
                  for name, t in self.trees.iteritems() ]
        lines += ['b %s %s' % (oid, name)
                  for name, oid in self.blobs.iteritems() ]
        return h.really_unicode('\n'.join(sorted(lines))).encode('utf-8')

    def __unicode__(self):
        return self.pretty_tree(recurse=False)

    def pretty_tree(self, indent=0, recurse=True, show_id=True):
        '''For debugging, show a nice tree representation'''
        lines = [' '*indent + 't %s %s' %
                 (name, '\n'+t.unicode_full_tree(indent+2, show_id=show_id) if recurse else t.hex())
                  for name, t in sorted(self.trees.iteritems()) ]
        lines += [' '*indent + 'b %s %s' % (name, oid if show_id else '')
                  for name, oid in sorted(self.blobs.iteritems()) ]
        output = h.really_unicode('\n'.join(lines)).encode('utf-8')
        return output

def topological_sort(graph):
    '''Return the topological sort of a graph.

    The graph is a dict with each entry representing
    a node (the key is the node ID) and its parent(s) (a
    set of node IDs). Result is an iterator over the topo-sorted
    node IDs.

    The algorithm is based on one seen in
    http://en.wikipedia.org/wiki/Topological_sorting#CITEREFKahn1962
    '''
    # Index children, identify roots
    children = defaultdict(list)
    roots = []
    for nid, parents in graph.items():
        if not parents:
            graph.pop(nid)
            roots.append(nid)
        for p_nid in parents: children[p_nid].append(nid)
    # Topo sort
    while roots:
        n = roots.pop()
        yield n
        for child in children[n]:
            graph[child].remove(n)
            if not graph[child]:
                graph.pop(child)
                roots.append(child)
    assert not graph, 'Cycle detected'


def prefix_paths_union(a, b):
    """
    Given two sets of paths, a and b, find the items from a that
    are either in b or are parent directories of items in b.
    """
    union = a & b
    prefixes = a - b
    candidates = b - a
    for prefix in prefixes:
        for candidate in candidates:
            if candidate.startswith(prefix + '/'):
                union.add(prefix)
                break
    return union


def zipdir(source, zipfile, exclude=None):
    """Create zip archive using zip binary."""
    zipbin = tg.config.get('scm.repos.tarball.zip_binary', '/usr/bin/zip')
    source = source.rstrip('/')
    # this is needed to get proper prefixes inside zip-file
    working_dir = os.path.dirname(source)
    source_fn = os.path.basename(source)
    command = [zipbin, '-y', '-q', '-r', zipfile, source_fn]
    if exclude:
        command += ['-x', exclude]
    p = Popen(command, cwd=working_dir, stdout=PIPE, stderr=PIPE)
    stdout, stderr = p.communicate()
    if p.returncode != 0:
        raise Exception(
            "Command: {0} returned non-zero exit code {1}\n"
            "STDOUT: {2}\n"
            "STDERR: {3}".format(command, p.returncode, stdout, stderr))


Mapper.compile_all()
