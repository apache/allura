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
from __future__ import annotations
import json
import os
import stat
from operator import itemgetter
import mimetypes
import logging
import string
import re
from subprocess import Popen, PIPE
from hashlib import sha1
from datetime import datetime, timedelta
from time import time
from collections import defaultdict, OrderedDict
from six.moves.urllib.parse import urljoin
from threading import Thread
from six.moves.queue import Queue
from itertools import chain, islice
import typing

import tg
from paste.deploy.converters import asint, asbool
from tg import tmpl_context as c
from tg import app_globals as g
import pymongo
import pymongo.errors
import bson
import six

from ming import schema as S
from ming.orm import session
from ming import Field, collection, Index
from ming.utils import LazyProperty
from ming.odm import FieldProperty, session, Mapper, mapper, MappedClass, RelationProperty
from ming.base import Object

from allura.lib import helpers as h
from allura.lib import utils
from allura.lib.security import has_access

from .artifact import Artifact, VersionedArtifact
from .auth import User
from .timeline import ActivityObject
from .monq_model import MonQTask
from .project import AppConfig
from .session import main_doc_session
from .session import repository_orm_session

if typing.TYPE_CHECKING:
    from ming.odm.mapper import Query


log = logging.getLogger(__name__)
config = utils.ConfigProxy(
    common_suffix='forgemail.domain',
)

README_RE = re.compile(r'^README(\.[^.]*)?$', re.IGNORECASE)
VIEWABLE_EXTENSIONS = frozenset([
    '.php', '.py', '.js', '.java', '.html', '.htm', '.yaml', '.sh',
    '.rb', '.phtml', '.txt', '.bat', '.ps1', '.xhtml', '.css', '.cfm', '.jsp', '.jspx',
    '.pl', '.php4', '.php3', '.rhtml', '.svg', '.markdown', '.json', '.ini', '.tcl', '.vbs', '.xsl'])


# Some schema types
SUser = dict(name=str, email=str, date=datetime)
SObjType = S.OneOf('blob', 'tree', 'submodule', 'symlink')

# Used for when we're going to batch queries using $in
QSIZE = 100
BINARY_EXTENSIONS = frozenset([
    ".3ds", ".3g2", ".3gp", ".7z", ".a", ".aac", ".adp", ".ai", ".aif", ".apk", ".ar", ".asf", ".au", ".avi", ".bak",
    ".bin", ".bk", ".bmp", ".btif", ".bz2", ".cab", ".caf", ".cgm", ".cmx", ".cpio", ".cr2", ".dat", ".deb", ".djvu",
    ".dll", ".dmg", ".dng", ".doc", ".docx", ".dra", ".DS_Store", ".dsk", ".dts", ".dtshd", ".dvb", ".dwg", ".dxf",
    ".ecelp4800", ".ecelp7470", ".ecelp9600", ".egg", ".eol", ".eot", ".epub", ".exe", ".f4v", ".fbs", ".fh", ".fla",
    ".flac", ".fli", ".flv", ".fpx", ".fst", ".fvt", ".g3", ".gif", ".gz", ".h261", ".h263", ".h264", ".ico", ".ief",
    ".img", ".ipa", ".iso", ".jar", ".jpeg", ".jpg", ".jpgv", ".jpm", ".jxr", ".ktx", ".lvp", ".lz", ".lzma", ".lzo",
    ".m3u", ".m4a", ".m4v", ".mar", ".mdi", ".mid", ".mj2", ".mka", ".mkv", ".mmr", ".mng", ".mov", ".movie", ".mp3",
    ".mp4", ".mp4a", ".mpeg", ".mpg", ".mpga", ".mxu", ".nef", ".npx", ".o", ".oga", ".ogg", ".ogv", ".otf", ".pbm",
    ".pcx", ".pdf", ".pea", ".pgm", ".pic", ".png", ".pnm", ".ppm", ".psd", ".pya", ".pyc", ".pyo", ".pyv", ".qt",
    ".rar", ".ras", ".raw", ".rgb", ".rip", ".rlc", ".rz", ".s3m", ".s7z", ".scpt", ".sgi", ".shar", ".sil", ".smv",
    ".so", ".sub", ".swf", ".tar", ".tbz2", ".tga", ".tgz", ".tif", ".tiff", ".tlz", ".ttf", ".uvh", ".uvi",
    ".uvm", ".uvp", ".uvs", ".uvu", ".viv", ".vob", ".war", ".wav", ".wax", ".wbmp", ".wdp", ".weba", ".webm", ".webp",
    ".whl", ".wm", ".wma", ".wmv", ".wmx", ".woff", ".woff2", ".wvx", ".xbm", ".xif", ".xm", ".xpi", ".xpm", ".xwd",
    ".xz", ".z", ".zip", ".zipx"
])

PYPELINE_EXTENSIONS = frozenset(utils.MARKDOWN_EXTENSIONS + ['.rst', '.textile', '.creole'])

DIFF_SIMILARITY_THRESHOLD = .5  # used for determining file renames


class RepositoryImplementation:

    # Repository-specific code
    def init(self):  # pragma no cover
        raise NotImplementedError('init')

    def clone_from(self, source_url):  # pragma no cover
        raise NotImplementedError('clone_from')

    def commit(self, revision):  # pragma no cover
        raise NotImplementedError('commit')

    def all_commit_ids(self):  # pragma no cover
        raise NotImplementedError('all_commit_ids')

    def new_commits(self, all_commits=False):  # pragma no cover
        '''Return a list of native commits in topological order (heads first).

        "commit" is a repo-native object, NOT a Commit object.
        If all_commits is False, only return commits not already indexed.
        '''
        raise NotImplementedError('new_commits')

    def commit_parents(self, commit):  # pragma no cover
        '''Return a list of native commits for the parents of the given (native)
        commit'''
        raise NotImplementedError('commit_parents')

    def refresh_commit_info(self, oid, seen, lazy=True):  # pragma no cover
        '''Refresh the data in the commit with id oid'''
        raise NotImplementedError('refresh_commit_info')

    def _setup_hooks(self, source_path=None):  # pragma no cover
        '''Install a hook in the repository that will ping the refresh url for
        the repo.  Optionally provide a path from which to copy existing hooks.'''
        raise NotImplementedError('_setup_hooks')

    # pragma no cover
    def log(self, revs=None, path=None, exclude=None, id_only=True, **kw):
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
        raise NotImplementedError('log')

    def compute_tree_new(self, commit, path='/'):  # pragma no cover
        '''Used in hg and svn to compute a git-like-tree lazily with the new models'''
        raise NotImplementedError('compute_tree')

    def open_blob(self, blob):  # pragma no cover
        '''Return a file-like object that contains the contents of the blob'''
        raise NotImplementedError('open_blob')

    def blob_size(self, blob):
        '''Return a blob size in bytes'''
        raise NotImplementedError('blob_size')

    def tarball(self, revision, path=None):
        '''Create a tarball for the revision'''
        raise NotImplementedError('tarball')

    def is_empty(self):
        '''Determine if the repository is empty by checking the filesystem'''
        raise NotImplementedError('is_empty')

    def is_file(self, path, rev=None):
        '''Determine if the repository is a file by checking the filesystem'''
        raise NotImplementedError('is_file')

    @classmethod
    def shorthand_for_commit(cls, oid):
        return '[%s]' % oid[:6]

    def symbolics_for_commit(self, commit):
        '''Return symbolic branch and tag names for a commit.'''
        raise NotImplementedError('symbolics_for_commit')

    def url_for_commit(self, commit, url_type='ci'):
        'return an URL, given either a commit or object id'
        if isinstance(commit, str):
            object_id = commit
        else:
            object_id = commit._id

        if '/' in object_id:
            object_id = os.path.join(
                object_id, self._repo.app.END_OF_REF_ESCAPE)

        return os.path.join(self._repo.url(), url_type, object_id) + '/'

    def _setup_paths(self, create_repo_dir=True):
        '''
        Ensure that the base directory in which the repo lives exists.
        If create_repo_dir is True, also ensure that the directory
        of the repo itself exists.
        '''
        if not self._repo.fs_path.endswith('/'):
            self._repo.fs_path += '/'
        fullname = self._repo.fs_path + self._repo.name
        # make the base dir for repo, regardless
        if not os.path.exists(self._repo.fs_path):
            os.makedirs(self._repo.fs_path)
        if create_repo_dir and not os.path.exists(fullname):
            os.mkdir(fullname)
        return fullname

    def _setup_special_files(self, source_path=None):
        magic_file = os.path.join(
            self._repo.fs_path, self._repo.name, tg.config.get(
                'scm.magic_file', '.ALLURA-REPOSITORY'))
        with open(magic_file, 'w') as f:
            f.write(six.ensure_text(self._repo.repo_id))
        os.chmod(magic_file, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        self._setup_hooks(source_path)

    @property
    def head(self):
        raise NotImplementedError('head')

    @property
    def heads(self):
        raise NotImplementedError('heads')

    @property
    def branches(self):
        raise NotImplementedError('branches')

    @property
    def tags(self):
        raise NotImplementedError('tags')

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
            chunks.put(paths[s:s + lcd_chunk_size])
            num_threads += 1

        def get_ids():
            paths = set(chunks.get())
            try:
                commit_id = commit._id
                while paths and commit_id:
                    if time() - start_time >= timeout:
                        log.error('last_commit_ids timeout for %s on %s',
                                  commit._id, ', '.join(paths))
                        break
                    commit_id, changes = self._get_last_commit(
                        commit._id, paths)
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
        raise NotImplementedError('get_changes')

    def paged_diffs(self, commit_id, start=0, end=None, onlyChangedFiles=False):
        """
        Returns files touched by the commit, grouped by status (added, removed,
        and changed) and the total number of such files.  Paginates according
        to :param start: and :param end:.
        """
        raise NotImplementedError('paged_diffs')

    def merge_request_commits(self, mr):
        """Given MergeRequest :param mr: return list of commits to be merged"""
        raise NotImplementedError('merge_request_commits')


class Repository(Artifact, ActivityObject):
    BATCH_SIZE = 100

    class __mongometa__:
        name = 'generic-repository'
        indexes = ['upstream_repo.name']

    query: 'Query[Repository]'

    _impl = None
    repo_id = 'repo'
    type_s = 'Repository'
    _refresh_precompute = True

    name = FieldProperty(str)
    tool = FieldProperty(str)
    fs_path = FieldProperty(str)
    url_path = FieldProperty(str)
    status = FieldProperty(str)
    additional_viewable_extensions = FieldProperty(str)
    heads = FieldProperty(S.Deprecated)
    branches = FieldProperty(S.Deprecated)
    repo_tags = FieldProperty(S.Deprecated)
    upstream_repo = FieldProperty(dict(name=str, url=str))
    default_branch_name = FieldProperty(str)
    cached_branches = FieldProperty([dict(name=str, object_id=str)])
    cached_tags = FieldProperty([dict(name=str, object_id=str)])

    def __init__(self, **kw):
        if 'name' in kw and 'tool' in kw:
            if kw.get('fs_path') is None:
                kw['fs_path'] = self.default_fs_path(c.project, kw['tool'])
            if kw.get('url_path') is None:
                kw['url_path'] = self.default_url_path(c.project, kw['tool'])
        super().__init__(**kw)

    @property
    def activity_name(self):
        return 'repo %s' % self.name

    @classmethod
    def default_fs_path(cls, project, tool):
        repos_root = tg.config.get('scm.repos.root', '/')
        # if a user-project, the repository path on disk needs to use the actual shortname
        # the nice url might have invalid chars
        return os.path.join(repos_root, tool, project.url(use_userproject_shortname=True)[1:])

    @classmethod
    def default_url_path(cls, project, tool):
        # if a user-project, the repository checkout path needs to use the actual shortname used on disk
        # not a nicer username (e.g. with underscores) used on web browsing urls
        return project.url(use_userproject_shortname=True)

    @property
    def tarball_path(self):
        return os.path.join(tg.config.get('scm.repos.tarball.root', '/'),
                            self.tool,
                            self.project.shortname[:1],
                            self.project.shortname[:2],
                            self.project.shortname,
                            self.name)

    @property
    def tarball_tmpdir(self):
        return os.path.join(tg.config.get('scm.repos.tarball.tmpdir', tg.config.get('scm.repos.tarball.root', '/')),
                            self.tool,
                            self.project.shortname[:1],
                            self.project.shortname[:2],
                            self.project.shortname,
                            self.name)

    def tarball_filename(self, revision, path=None):
        shortname = c.project.shortname.replace('/', '-')
        mount_point = c.app.config.options.mount_point
        filename = f'{shortname}-{mount_point}-{revision}'
        return filename

    def tarball_url(self, revision, path=None):
        filename = '{}{}'.format(self.tarball_filename(revision, path), '.zip')
        r = os.path.join(self.tool,
                         self.project.shortname[:1],
                         self.project.shortname[:2],
                         self.project.shortname,
                         self.name,
                         filename)
        return urljoin(tg.config.get('scm.repos.tarball.url_prefix', '/'), r)

    def get_tarball_status(self, revision, path=None):
        pathname = os.path.join(
            self.tarball_path, self.tarball_filename(revision, path))
        filename = '{}{}'.format(pathname, '.zip')
        if os.path.isfile(filename.encode('utf-8')):
            return 'complete'

        # file doesn't exist, check for busy task
        task = MonQTask.query.get(**{
            'task_name': 'allura.tasks.repo_tasks.tarball',
            'args': [revision, path or ''],
            'state': {'$in': ['busy', 'ready']},
        })

        return task.state if task else None

    def __repr__(self):  # pragma no cover
        return '<{} {}>'.format(
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

    def get_tags(self, for_merge_request=False):
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

    def paged_diffs(self, commit_id, start=0, end=None, onlyChangedFiles=False):
        return self._impl.paged_diffs(commit_id, start, end, onlyChangedFiles)

    def init_as_clone(self, source_path, source_name, source_url):
        self.upstream_repo.name = source_name
        self.upstream_repo.url = source_url
        session(self).flush(self)
        source = source_path if source_path else source_url
        self._impl.clone_from(source)
        log.info('... %r cloned', self)
        g.post_event('repo_cloned', source_url, source_path)
        self.refresh(notify=False, new_clone=True)

    def log(self, revs=None, path=None, exclude=None, id_only=True, limit=None, **kw):
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
        log_iter = self._impl.log(revs, path, exclude=exclude, id_only=id_only, limit=limit, **kw)
        return islice(log_iter, limit)

    def latest(self, branch=None):
        if self._impl is None:
            return None
        if branch is None:
            branch = self.app.default_branch_name
        try:
            return self.commit(branch)
        except Exception:
            log.exception('Cannot get latest commit for a branch: %s', branch)
            return None

    def url(self):
        return self.app_config.url()

    def refresh_url(self):
        refresh_base_url = tg.config.get('scm.repos.refresh_base_url') or tg.config.get('base_url', 'http://localhost:8080')
        return '/'.join([
            refresh_base_url.rstrip('/'),
            'auth/refresh_repo',
            self.url().lstrip('/'),
        ])

    def shorthand_id(self):
        return self.name

    @property
    def email_address(self):
        return f'noreply@{self.email_domain}{config.common_suffix}'

    def index(self):
        result = Artifact.index(self)
        result.update(
            name_s=self.name,
            type_s=self.type_s,
            title=f'{self.project.name} {self.app.tool_label} repository')
        return result

    @property
    def full_fs_path(self):
        return os.path.join(self.fs_path, self.name)

    def suggested_clone_dest_path(self):
        owning_user = c.project.user_project_of
        if owning_user:
            projname = owning_user.username
        else:
            projname = c.project.shortname.replace('/', '-')
        return f'{projname}-{self.name}'

    def clone_url(self, category, username=''):
        '''Return a URL string suitable for copy/paste that describes _this_ repo,
           e.g., for use in a clone/checkout command
        '''
        if self.app.config.options.get('external_checkout_url', None):
            tpl = string.Template(self.app.config.options.external_checkout_url)
        else:
            tpl = string.Template(tg.config.get(f'scm.host.{category}.{self.tool}'))
        url = tpl.substitute(dict(username=username, path=self.url_path + self.name))
        # this is an svn option, but keeps clone_*() code from diverging
        url += self.app.config.options.get('checkout_url', '')
        return url

    def clone_url_first(self, anon, username=''):
        '''
        Get first clone_url option, useful for places where we need to show just one

        :param bool anon: Anonymous or not
        :param str username: optional
        '''
        cat = self.clone_command_categories(anon=anon)[0]['key']
        return self.clone_url(cat, username)

    def clone_command(self, category, username=''):
        '''Return a string suitable for copy/paste that would clone this repo locally
        '''
        if not username and c.user not in (None, User.anonymous()):
            username = c.user.username
        tpl = string.Template(tg.config.get(f'scm.clone.{category}.{self.tool}') or
                              tg.config.get('scm.clone.%s' % self.tool))
        return tpl.substitute(dict(username=username,
                                   source_url=self.clone_url(category, username),
                                   dest_path=self.suggested_clone_dest_path()))

    def clone_command_first(self, anon, username=''):
        '''
        Get first clone_command option, useful for places where we need to show just one

        :param bool anon: Anonymous or not
        :param str username: optional
        '''
        cat = self.clone_command_categories(anon=anon)[0]['key']
        return self.clone_command(cat, username)

    def clone_command_categories(self, anon):
        conf = tg.config.get('scm.clonechoices{}.{}'.format('_anon' if anon else '', self.tool))
        if not conf and anon:
            # check for a non-anon config
            conf = tg.config.get(f'scm.clonechoices.{self.tool}')
        if conf:
            return json.loads(conf)
        elif anon:
            # defaults to match historical scm.clone.* configs, in case someone updates Allura but not their .ini
            return [{"name": "RO", "key": "ro", "title": "Read Only"},
                    {"name": "HTTPS", "key": "https_anon", "title": "HTTPS"}]
        else:
            return [{"name": "RW", "key": "rw", "title": "Read/Write"},
                    {"name": "RO", "key": "ro", "title": "Read Only"},
                    {"name": "HTTPS", "key": "https", "title": "HTTPS"}]

    def merge_requests_by_statuses(self, *statuses):
        return MergeRequest.query.find(dict(
            app_config_id=self.app.config._id,
            status={'$in': statuses})).sort(
            'request_number')

    def all_merge_requests(self):
        return MergeRequest.query.find(dict(
            app_config_id=self.app.config._id)).sort(
            'request_number')

    @LazyProperty
    def _additional_viewable_extensions(self):
        ext_list = self.additional_viewable_extensions or ''
        ext_list = [ext.strip() for ext in ext_list.split(',') if ext]
        ext_list += ['.ini', '.gitignore', '.svnignore', 'README']
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
        from allura.model.repo_refresh import unknown_commit_ids as unknown_commit_ids_repo
        return unknown_commit_ids_repo(self.all_commit_ids())

    def refresh(self, all_commits=False, notify=True, new_clone=False, commits_are_new=None):
        '''Find any new commits in the repository and update'''
        try:
            from allura.model.repo_refresh import refresh_repo
            log.info('... %r analyzing', self)
            self.set_status('analyzing')
            refresh_repo(self, all_commits, notify, new_clone, commits_are_new)
        finally:
            log.info('... %s ready', self)
            self.set_status('ready')

    def push_upstream_context(self):
        project, rest = h.find_project(self.upstream_repo.name)
        with h.push_context(project._id):
            app = project.app_instance(rest[0])
        return h.push_context(project._id, app_config_id=app.config._id)

    def pending_upstream_merges(self):
        q = {
            'downstream.project_id': self.project_id,
            'downstream.mount_point': self.app.config.options.mount_point,
            'status': 'open'}
        with self.push_upstream_context():
            return MergeRequest.query.find(q).count()

    @property
    def forks(self):
        all_forks = self.query.find({'upstream_repo.name': self.url()}).all()
        return [fork for fork in all_forks if fork.app_config is not None
                      and fork.app_config.project is not None]

    def tarball(self, revision, path=None):
        if path:
            path = path.strip('/')
        self._impl.tarball(revision, path)

    def rev_to_commit_id(self, rev):
        raise NotImplementedError('rev_to_commit_id')

    def set_status(self, status):
        '''
        Update (and flush) the repo status indicator.

        Updates to the repo status (or any Repository field) are considered
        project updates (because Repositories are Artifacts; see
        `Artifact.__mongometa__.before_save`) and thus change `last_updated`
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

    def get_default_branch(self, default_branch_name):
        branch_name = getattr(self, 'default_branch_name', None) or default_branch_name
        branches = []
        if not self.is_empty():
            branches = [b.name for b in self.get_branches()]

        if branches and branch_name not in branches:
            if default_branch_name in branches:
                branch_name = default_branch_name
            else:
                branch_name = branches[0]
            self.set_default_branch(branch_name)
        return branch_name

    def merge_request_commits(self, mr):
        """Given MergeRequest :param mr: return list of commits to be merged"""
        return self._impl.merge_request_commits(mr)


class MergeRequest(VersionedArtifact, ActivityObject):
    statuses = ['open', 'merged', 'rejected']

    class __mongometa__:
        name = 'merge-request'
        indexes = ['commit_id', 'creator_id']
        unique_indexes = [('app_config_id', 'request_number')]

    query: 'Query[MergeRequest]'

    type_s = 'MergeRequest'

    request_number = FieldProperty(int)
    status = FieldProperty(str, if_missing='open')
    downstream = FieldProperty(dict(
        project_id=S.ObjectId,
        mount_point=str,
        commit_id=str))
    source_branch = FieldProperty(str, if_missing='')
    target_branch = FieldProperty(str)
    creator_id = FieldProperty(S.ObjectId, if_missing=lambda: c.user._id)
    created = FieldProperty(datetime, if_missing=datetime.utcnow)
    summary = FieldProperty(str)
    description = FieldProperty(str)
    can_merge_cache = FieldProperty({str: bool})
    new_commits = FieldProperty([S.Anything], if_missing=None)  # don't access directly, use `commits` property

    @property
    def activity_name(self):
        return 'merge request #%s' % self.request_number

    @property
    def type_name(self):
        return 'merge request'

    @property
    def activity_extras(self):
        d = ActivityObject.activity_extras.fget(self)
        d.update(summary=self.summary)
        return d

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
    def downstream_repo(self):
        with self.push_downstream_context():
            return c.app.repo

    def push_downstream_context(self):
        return h.push_context(self.downstream.project_id, self.downstream.mount_point)

    @property
    def commits(self):
        if self.new_commits is not None:
            return self.new_commits

        with self.push_downstream_context():
            # update the cache key only, being careful not to touch anything else that ming will try to flush later
            # this avoids race conditions with the `set_can_merge_cache()` caching and clobbering fields
            new_commits = c.app.repo.merge_request_commits(self)
            self.query.update({'$set': {'new_commits': new_commits}})
            return new_commits

    @classmethod
    def upsert(cls, **kw):
        num = cls.query.find(dict(
            app_config_id=c.app.config._id)).count() + 1
        while True:
            try:
                r = cls(request_number=num, **kw)
                session(r).flush(r)
                return r
            except pymongo.errors.DuplicateKeyError:  # pragma no cover
                session(r).expunge(r)
                num += 1

    def url(self):
        return self.app.url + 'merge-requests/%s/' % self.request_number

    def index(self):
        result = Artifact.index(self)
        result.update(
            name_s='Merge Request #%d' % self.request_number,
            type_s=self.type_s,
            title='Merge Request #%d: %s' % (self.request_number, self.summary),
        )
        return result

    @property
    def email_subject(self):
        return 'Merge request: ' + self.summary

    def merge_allowed(self, user):
        """
        Returns true if a merge is allowed by system and tool configuration.
        """
        if not self.app.forkable:
            return False
        if self.status != 'open':
            return False
        if asbool(tg.config.get(f'scm.merge.{self.app.config.tool_name}.disabled')):
            return False
        if not h.has_access(self.app, 'write', user):
            return False
        if self.app.config.options.get('merge_disabled'):
            return False
        return True

    def can_merge_cache_key(self):
        """
        Returns key for can_merge_cache constructed from current
        source & target branch commits.
        """
        source_hash = self.downstream.commit_id
        target_hash = self.app.repo.commit(self.target_branch)._id
        key = f'{source_hash}-{target_hash}'
        return key

    def get_can_merge_cache(self):
        """Returns True/False or None in case of cache miss."""
        key = self.can_merge_cache_key()
        return self.can_merge_cache.get(key)

    def set_can_merge_cache(self, val):
        key = self.can_merge_cache_key()
        # update the cache key only, being careful not to touch anything else that ming will try to flush later
        # this avoids race conditions with the `commits()` caching and clobbering fields
        can_merge_cache = self.can_merge_cache._deinstrument()
        can_merge_cache[key] = val
        self.query.update({'$set': {'can_merge_cache': can_merge_cache}})

    def can_merge(self):
        """
        Returns boolean indicating if automatic merge is possible (no
        conflicts). If result is unknown yet, returns None and fires a task to
        get the result. Caches result for later reuse.
        """
        if not self.merge_allowed(c.user):
            return None
        if self.status == 'merged':
            return True
        cached = self.get_can_merge_cache()
        if cached is not None:
            return cached
        in_progress = self.can_merge_task_status() in ['ready', 'busy']
        if self.app.forkable and not in_progress:
            from allura.tasks import repo_tasks
            repo_tasks.can_merge.post(self._id)

    def merge(self):
        in_progress = self.merge_task_status() in ['ready', 'busy']
        if self.app.forkable and not in_progress:
            from allura.tasks import repo_tasks
            repo_tasks.merge.post(self._id)

    def _task_status(self, task_name):
        task = MonQTask.query.find({
            'state': {'$in': ['busy', 'complete', 'error', 'ready']},  # needed to use index
            'task_name': task_name,
            'args': [self._id],
            'time_queue': {'$gt': datetime.utcnow() - timedelta(days=1)},  # constrain on index further
        }).sort('_id', -1).limit(1).first()
        if task:
            return task.state
        return None

    def merge_task_status(self):
        return self._task_status('allura.tasks.repo_tasks.merge')

    def can_merge_task_status(self):
        return self._task_status('allura.tasks.repo_tasks.can_merge')

    def commits_task_status(self):
        return self._task_status('allura.tasks.repo_tasks.determine_mr_commits')

    def add_meta_post(self, changes):
        tmpl = g.jinja2_env.get_template('allura:templates/repo/merge_request_changed.html')
        message = tmpl.render(changes=changes)
        self.discussion_thread.add_post(text=message, is_meta=True, ignore_security=True)


class RepoObject:

    def __repr__(self):  # pragma no cover
        return '<{} {}>'.format(
            self.__class__.__name__, self._id)

    def primary(self):
        return self

    def index_id(self):
        '''Globally unique artifact identifier.  Used for
        SOLR ID, shortlinks, and maybe elsewhere
        '''
        id = '{}.{}#{}'.format(
            'allura.model.repo',  # preserve index_id after module consolidation
            self.__class__.__name__,
            self._id)
        return id.replace('.', '/')

    @classmethod
    def upsert(cls, id, **kwargs):
        isnew = False
        r = cls.query.get(_id=id)
        if r is not None:
            return r, isnew
        try:
            r = cls(_id=id, **kwargs)
            session(r).flush(r)
            isnew = True
        except pymongo.errors.DuplicateKeyError:  # pragma no cover
            session(r).expunge(r)
            r = cls.query.get(_id=id)
        return r, isnew


# this is duplicative with the Commit model
# would be nice to get rid of this "doc" based view, but it is used a lot
CommitDoc = collection(
    'repo_ci', main_doc_session,
    Field('_id', str),
    Field('tree_id', str),
    Field('committed', SUser),
    Field('authored', SUser),
    Field('message', str),
    Field('parent_ids', [str], index=True),
    Field('child_ids', [str], index=True),
    Field('repo_ids', [S.ObjectId()], index=True))


class CommitStatus(MappedClass):
    class __mongometa__:
        session = repository_orm_session
        name = 'commit_status'
        indexes = [('commit_id', 'context'),]

    query: 'Query[CommitStatus]'

    _id = FieldProperty(S.ObjectId)
    state = FieldProperty(str)
    target_url = FieldProperty(str)
    description = FieldProperty(str)
    context = FieldProperty(str)
    commit_id = FieldProperty(str)
    commit = RelationProperty('Commit')

    def __init__(self, **kw):
        assert 'commit_id' in kw, 'Commit id missing'
        super().__init__(**kw)

    @classmethod
    def upsert(cls, **kw):
        obj = cls.query.find_and_modify(
            query=dict(commit_id=kw.get('commit_id'), context=kw.get('context')),
            update={'$set': kw},
            new=True,
            upsert=True,
        )
        return obj


class Commit(MappedClass, RepoObject, ActivityObject):
    # Basic commit information
    # One of these for each commit in the physical repo on disk

    class __mongometa__:
        session = repository_orm_session
        name = 'repo_ci'
        indexes = [
            'parent_ids',
            'child_ids',
            'repo_ids',
        ]

    query: 'Query[Commit]'

    _id = FieldProperty(str)  # hexsha of the commit (for Git and Hg)
    tree_id = FieldProperty(str)
    committed = FieldProperty(SUser)
    authored = FieldProperty(SUser)
    message = FieldProperty(str)
    parent_ids = FieldProperty([str])
    child_ids = FieldProperty([str])
    repo_ids = FieldProperty([S.ObjectId()])
    statuses = RelationProperty('CommitStatus', via="commit_id")

    type_s = 'Commit'
    # Ephemeral attrs
    repo = None

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

    @property
    def activity_name(self):
        return self.shorthand_id()

    @property
    def activity_extras(self):
        d = ActivityObject.activity_extras.fget(self)
        d.update(summary=self._summary(limit=500))
        if self.repo:
            d.update(app_config_id=self.repo.app.config._id)
        return d

    def has_activity_access(self, perm, user, activity):
        """
        Check access against the original app.

        Commits have no ACLs and are therefore always viewable by any user, if
        they have access to the tool.
        """
        app_config_id = activity.obj.activity_extras.get('app_config_id')
        if app_config_id:
            app_config = AppConfig.query.get(_id=app_config_id)
            return has_access(app_config, perm, user)
        return True

    def set_context(self, repo):
        self.repo = repo

    @LazyProperty
    def authored_user(self):
        return User.by_email_address(self.authored.email)

    @LazyProperty
    def committed_user(self):
        return User.by_email_address(self.committed.email)

    @LazyProperty
    def author_url(self):
        u = self.authored_user
        if u:
            return u.url()

    @LazyProperty
    def committer_url(self):
        u = self.committed_user
        if u:
            return u.url()

    @LazyProperty
    def tree(self):
        return self.get_tree(create=True)

    def get_tree(self, create=True):
        if self.tree_id is None and create:
            self.tree_id = self.repo.compute_tree_new(self)
        if self.tree_id is None:
            return None
        cache = getattr(c, 'model_cache', '') or ModelCache()
        t = cache.get(Tree, dict(_id=self.tree_id))
        if t is None and create:
            self.tree_id = self.repo.compute_tree_new(self)
            t = Tree.query.get(_id=self.tree_id)
            cache.set(Tree, dict(_id=self.tree_id), t)
        if t is not None:
            t.set_context(self)
        return t

    @LazyProperty
    def summary(self):
        return self._summary()

    def _summary(self, limit=50):
        message = h.really_unicode(self.message)
        first_line = message.split('\n')[0]
        return h.text.truncate(first_line, limit)

    def shorthand_id(self):
        if self.repo is None:
            self.repo = self.guess_repo()
        if self.repo is None:
            return repr(self)
        return self.repo.shorthand_for_commit(self._id)

    @LazyProperty
    def symbolic_ids(self):
        return self.repo.symbolics_for_commit(self)

    def url(self):
        if self.repo is None:
            self.repo = self.guess_repo()
        if self.repo is None:
            return '#'
        return self.repo.url_for_commit(self)

    def guess_repo(self):
        import traceback
        log.error('guess_repo should not be called: %s' %
                  ''.join(traceback.format_stack()))
        for ac in c.project.app_configs:
            try:
                app = c.project.app_instance(ac)
                if app.repo._id in self.repo_ids:
                    return app.repo
            except AttributeError:
                pass
        return None

    def link_text(self):
        '''The link text that will be used when a shortlink to this artifact
        is expanded into an <a></a> tag.

        By default this method returns type_s + shorthand_id(). Subclasses should
        override this method to provide more descriptive link text.
        '''
        return self.shorthand_id()

    def context(self):
        result = dict(prev=None, next=None)
        if self.parent_ids:
            result['prev'] = self.query.find(
                dict(_id={'$in': self.parent_ids})).all()
            for ci in result['prev']:
                ci.set_context(self.repo)
        if self.child_ids:
            result['next'] = self.query.find(
                dict(_id={'$in': self.child_ids})).all()
            for ci in result['next']:
                ci.set_context(self.repo)
        return result

    @LazyProperty
    def diffs(self):
        return self.paged_diffs()

    def paged_diffs(self, start=0, end=None, onlyChangedFiles=False):
        diffs = self.repo.paged_diffs(self._id, start, end, onlyChangedFiles)

        return Object(
            added=sorted(diffs['added']),
            removed=sorted(diffs['removed']),
            changed=sorted(diffs['changed']),
            copied=sorted(diffs['copied'], key=itemgetter('new', 'old')),  # this is a list of dicts
            renamed=sorted(diffs['renamed'], key=itemgetter('new', 'old')),  # this is a list of dicts
            total=diffs['total'])

    def get_path(self, path, create=True):
        path = path.lstrip('/')
        parts = path.split('/')
        cur = self.get_tree(create)
        if cur is not None:
            for part in parts:
                if part != '':
                    cur = cur[part]
        return cur

    @LazyProperty
    def changed_paths(self):
        '''
        Returns a list of paths changed in this commit.
        Leading and trailing slashes are removed, and
        the list is complete, meaning that if a sub-path
        is changed, all of the parent paths are included
        (including '' to represent the root path).

        Example:

            If the file /foo/bar is changed in the commit,
            this would return ['', 'foo', 'foo/bar']
        '''
        changes = self.repo.get_changes(self._id)
        changed_paths = set()
        for change in changes:
            node = h.really_unicode(change).strip('/')
            changed_paths.add(node)
            node_path = os.path.dirname(node)
            while node_path:
                changed_paths.add(node_path)
                node_path = os.path.dirname(node_path)
            changed_paths.add('')  # include '/' if there are any changes
        return changed_paths

    @LazyProperty
    def added_paths(self):
        '''
        Returns a list of paths added in this commit.
        Leading and trailing slashes are removed, and
        the list is complete, meaning that if a directory
        with subdirectories is added, all of the child
        paths are included (this relies on the :meth paged_diffs:
        being complete).

        Example:

            If the directory /foo/bar/ is added in the commit
            which contains a subdirectory /foo/bar/baz/ with
            the file /foo/bar/baz/qux.txt, this would return:
            ['foo/bar', 'foo/bar/baz', 'foo/bar/baz/qux.txt']
        '''
        paths = set()
        for path in self.paged_diffs()['added']:
            paths.add(path.strip('/'))
        return paths

    @LazyProperty
    def info(self):
        return dict(
            id=self._id,
            author=self.authored.name,
            author_email=self.authored.email,
            date=self.authored.date,
            author_url=self.author_url,
            shortlink=self.shorthand_id(),
            summary=self.summary
        )

    @LazyProperty
    def webhook_info(self):
        return {
            'id': self._id,
            'url': h.absurl(self.url()),
            'timestamp': self.authored.date,
            'message': self.summary,
            'author': {
                'name': self.authored.name,
                'email': self.authored.email,
                'username': self.authored_user.username if self.authored_user else '',
            },
            'committer': {
                'name': self.committed.name,
                'email': self.committed.email,
                'username': self.committed_user.username if self.committed_user else '',
            },
            'added': self.diffs.added,
            'removed': self.diffs.removed,
            'modified': self.diffs.changed,
            'copied': self.diffs.copied,
            'renamed': self.diffs.renamed,
        }


class Tree(MappedClass, RepoObject):
    # Basic tree information
    class __mongometa__:
        session = repository_orm_session
        name = 'repo_tree'
        indexes = [
        ]

    query: 'Query[Tree]'

    _id = FieldProperty(str)
    tree_ids = FieldProperty([dict(name=str, id=str)])
    blob_ids = FieldProperty([dict(name=str, id=str)])
    other_ids = FieldProperty([dict(name=str, id=str, type=SObjType)])

    # Ephemeral attrs
    repo = None
    commit = None
    parent = None
    name = None

    def __getitem__(self, name: str) -> Tree | Blob:
        cache = getattr(c, 'model_cache', '') or ModelCache()
        obj = self.by_name[name]
        if obj['type'] == 'blob':
            return Blob(self, name, obj['id'])
        if obj['type'] == 'submodule':
            log.info('Skipping submodule "%s"' % name)
            raise KeyError(name)
        if obj['type'] == 'symlink':
            return Symlink(self, name, obj['id'])
        obj = cache.get(Tree, dict(_id=obj['id']))
        if obj is None:
            oid = self.repo.compute_tree_new(
                self.commit, self.path() + name + '/')
            obj = cache.get(Tree, dict(_id=oid))
        if obj is None:
            raise KeyError(name)
        obj.set_context(self, name)
        return obj

    def get_obj_by_path(self, path):
        if hasattr(path, 'get'):
            path = path['new']
        if path.startswith('/'):
            path = path[1:]
        path = path.split('/')
        obj = self
        for p in path:
            if isinstance(obj, Blob):  # normally is Tree
                # can get a Blob (incl git symlink in past) if it changed type in a commit
                return None
            try:
                obj = obj[p]
            except KeyError:
                return None
        return obj

    def get_blob_by_path(self, path):
        obj = self.get_obj_by_path(path)
        return obj if isinstance(obj, Blob) else None

    def set_context(self, commit_or_tree, name=None):
        assert commit_or_tree is not self
        self.repo = commit_or_tree.repo
        if name:
            self.commit = commit_or_tree.commit
            self.parent = commit_or_tree
            self.name = name
        else:
            self.commit = commit_or_tree

    def readme(self):
        'returns (filename, unicode text) if a readme file is found'
        for x in self.blob_ids:
            if README_RE.match(x.name):
                name = x.name
                blob = self[name]
                return (x.name, h.really_unicode(blob.text))
        return None, None

    def ls(self):
        '''
        List the entries in this tree, with historical commit info for
        each node.
        '''
        last_commit = LastCommit.get(self)
        # ensure that the LCD is saved, even if
        # there is an error later in the request
        if last_commit:
            session(last_commit).flush(last_commit)
            return self._lcd_map(last_commit)
        else:
            return []

    def _lcd_map(self, lcd):
        '''
        Map "last-commit docs" to the structure that templates expect.

        (This exists because LCD logic changed in the past, whereas templates
        were not changed)
        '''
        if lcd is None:
            return []
        commit_ids = [e.commit_id for e in lcd.entries]
        commits = list(Commit.query.find(dict(_id={'$in': commit_ids})))
        for commit in commits:
            commit.set_context(self.repo)
        commit_infos = {c._id: c.info for c in commits}
        tree_names = sorted(n.name for n in self.tree_ids)
        blob_names = sorted(n.name for n in self.blob_ids)
        other_names = sorted(n.name for n in self.other_ids)

        results = []
        for type, names in (('DIR', tree_names), ('BLOB', blob_names), ('OTHER', other_names)):
            for name in names:
                commit_info = commit_infos.get(lcd.by_name.get(name))
                if not commit_info:
                    commit_info = defaultdict(str)
                elif 'id' in commit_info:
                    commit_info['href'] = self.repo.url_for_commit(
                        commit_info['id'])
                results.append(dict(
                    kind=type,
                    name=name,
                    href=name,
                    last_commit=dict(
                        author=commit_info['author'],
                        author_email=commit_info['author_email'],
                        author_url=commit_info['author_url'],
                        date=commit_info.get('date'),
                        href=commit_info.get('href', ''),
                        shortlink=commit_info['shortlink'],
                        summary=commit_info['summary'],
                    ),
                ))
        return results

    def path(self):
        if self.parent:
            assert self.parent is not self
            return self.parent.path() + self.name + '/'
        else:
            return '/'

    def url(self):
        return self.commit.url() + 'tree' + self.path()

    @LazyProperty
    def by_name(self):
        d = Object((x.name, x) for x in self.other_ids)
        d.update(
            (x.name, Object(x, type='tree'))
            for x in self.tree_ids)
        d.update(
            (x.name, Object(x, type='blob'))
            for x in self.blob_ids)
        return d

    def is_blob(self, name):
        return self.by_name[name]['type'] == 'blob'

    def get_blob(self, name):
        x = self.by_name[name]
        return Blob(self, name, x.id)


class Blob:
    '''Lightweight object representing a file in the repo'''

    def __init__(self, tree, name, _id):
        self._id = _id
        self.tree = tree
        self.name = name
        self.repo = tree.repo
        self.commit = tree.commit
        fn, ext = os.path.splitext(self.name)
        self.extension = ext or fn

    def path(self):
        return self.tree.path() + h.really_unicode(self.name)

    def url(self):
        return self.tree.url() + h.really_unicode(self.name)

    @LazyProperty
    def _content_type_encoding(self):
        return self.repo.guess_type(self.name)

    @LazyProperty
    def content_type(self):
        return self._content_type_encoding[0]

    @LazyProperty
    def content_encoding(self):
        return self._content_type_encoding[1]

    @property
    def has_pypeline_view(self):
        if README_RE.match(self.name) or self.extension in PYPELINE_EXTENSIONS:
            return True
        return False

    @LazyProperty
    def has_html_view(self):
        '''
        Return true if file is a text file that can be displayed.
        :return: boolean
        '''
        if self.extension in self.repo._additional_viewable_extensions:
            return True
        if self.extension in BINARY_EXTENSIONS:
            return False
        if (self.content_type.startswith('text/') or
                self.extension in VIEWABLE_EXTENSIONS or
                self.extension in PYPELINE_EXTENSIONS or
                utils.is_text_file(self.text)):
            return True
        return False

    @property
    def has_image_view(self):
        return self.content_type.startswith('image/')

    def open(self):
        return self.repo.open_blob(self)

    def __iter__(self):
        return iter(self.open())

    @LazyProperty
    def size(self):
        return self.repo.blob_size(self)

    @LazyProperty
    def text(self):
        """
        Direct binary contents of file.  Convert with h.really_unicode() if you think it is textual.
        """
        return self.open().read()


class EmptyBlob(Blob):
    def __init__(self):
        pass

    def open(self):
        return ''

    @property
    def size(self):
        return 0

    def __bool__(self):
        return False


class Symlink(Blob):
    # maybe this shouldn't inherit from Blob, but its handy for now and works well with git (where symlinks are blobs)
    pass


# this is duplicative with the LastCommit model
# would be nice to get rid of this "doc" based view, but it is used a lot
LastCommitDoc = collection(
    'repo_last_commit', main_doc_session,
    Field('_id', S.ObjectId()),
    Field('commit_id', str),
    Field('path', str),
    Index('commit_id', 'path'),
    Field('entries', [dict(
        name=str,
        commit_id=str)]))


class LastCommit(MappedClass, RepoObject):
    # Information about the last commit to touch a tree
    class __mongometa__:
        session = repository_orm_session
        name = 'repo_last_commit'
        indexes = [
            ('commit_id', 'path'),
        ]

    query: 'Query[LastCommit]'

    _id = FieldProperty(S.ObjectId)
    commit_id = FieldProperty(str)
    path = FieldProperty(str)
    entries = FieldProperty([dict(
        name=str,
        commit_id=str,
    )])

    def __repr__(self):
        return f'<LastCommit /{self.path!r} {self.commit_id}>'

    @classmethod
    def _last_commit_id(cls, commit, path):
        if path == '':
            # on the top-level dir, the relevant commit should always be the current commit
            return commit._id
        try:
            rev = next(commit.repo.log(commit._id, path, id_only=True, limit=1))
            return commit.repo.rev_to_commit_id(rev)
        except StopIteration:
            log.error('Tree node not recognized by SCM: %s @ %s',
                      path, commit._id)
            return commit._id

    @classmethod
    def _prev_commit_id(cls, commit, path):
        if not commit.parent_ids or path in commit.added_paths:
            return None  # new paths by definition have no previous LCD
        lcid_cache = getattr(c, 'lcid_cache', '')
        if lcid_cache != '' and path in lcid_cache:
            return lcid_cache[path]
        try:
            log_iter = commit.repo.log(commit._id, path, id_only=True, limit=2)
            next(log_iter)
            rev = next(log_iter)
            return commit.repo.rev_to_commit_id(rev)
        except StopIteration:
            return None

    @classmethod
    def get(cls, tree):
        '''Find or build the LastCommitDoc for the given tree.'''
        cache = getattr(c, 'model_cache', '') or ModelCache()
        path = tree.path().strip('/')
        last_commit_id = cls._last_commit_id(tree.commit, path)
        lcd = cache.get(cls, {'path': path, 'commit_id': last_commit_id})
        if lcd is None:
            commit = cache.get(Commit, {'_id': last_commit_id})
            commit.set_context(tree.repo)
            lcd = cls._build(commit.get_path(path))
        return lcd

    @classmethod
    def _build(cls, tree):
        '''
          Build the LCD record, presuming that this tree is where it was most
          recently changed.
        '''
        model_cache = getattr(c, 'model_cache', '') or ModelCache()
        path = tree.path().strip('/')
        entries = []
        prev_lcd = None
        prev_lcd_cid = cls._prev_commit_id(tree.commit, path)
        if prev_lcd_cid:
            prev_lcd = model_cache.get(
                cls, {'path': path, 'commit_id': prev_lcd_cid})
        entries = {}
        nodes = {
            node.name for node in chain(tree.tree_ids, tree.blob_ids, tree.other_ids)}
        changed = {
            node for node in nodes if os.path.join(path, node) in tree.commit.changed_paths}
        unchanged = [os.path.join(path, node) for node in nodes - changed]
        if prev_lcd:
            # get unchanged entries from previously computed LCD
            entries = prev_lcd.by_name
        elif unchanged:
            # no previously computed LCD, so get unchanged entries from SCM
            # (but only ask for the ones that we know we need)
            entries = tree.commit.repo.last_commit_ids(tree.commit, unchanged)
            if entries is None:
                # something strange went wrong; still show the list of files
                # and possibly try again later
                entries = {}
            # paths are fully-qualified; shorten them back to just node names
            entries = {
                os.path.basename(path): commit_id for path, commit_id in entries.items()}
        # update with the nodes changed in this tree's commit
        entries.update({node: tree.commit._id for node in changed})
        # convert to a list of dicts, since mongo doesn't handle arbitrary keys
        # well (i.e., . and $ not allowed)
        entries = [{'name': name, 'commit_id': value}
                   for name, value in entries.items()]
        lcd = cls(
            commit_id=tree.commit._id,
            path=path,
            entries=entries,
        )
        model_cache.set(cls, {'path': path, 'commit_id': tree.commit._id}, lcd)
        return lcd

    @LazyProperty
    def by_name(self):
        return {n.name: n.commit_id for n in self.entries}


class ModelCache:

    '''
    Cache model instances based on query params passed to get.  LRU cache.

    This does more caching than ming sessions (which only cache individual objects by _id)

    The added complexity here may be unnecessary premature optimization, but
    should be quite helpful when building up many models in order, like lcd _build
    for a series of several new commits.
    '''

    def __init__(self, max_instances=None, max_queries=None):
        '''
        By default, each model type can have 2000 instances and
        8000 queries.  You can override these for specific model
        types by passing in a dict() for either max_instances or
        max_queries keyed by the class(es) with the max values.
        Classes not in the dict() will use the default 2000/8000
        default.

        If you pass in a number instead of a dict, that value will
        be used as the max for all classes.
        '''
        max_instances_default = 2000
        max_queries_default = 8000
        if isinstance(max_instances, int):
            max_instances_default = max_instances
        if isinstance(max_queries, int):
            max_queries_default = max_queries
        self._max_instances = defaultdict(lambda: max_instances_default)
        self._max_queries = defaultdict(lambda: max_queries_default)
        if hasattr(max_instances, 'items'):
            self._max_instances.update(max_instances)
        if hasattr(max_queries, 'items'):
            self._max_queries.update(max_queries)

        # keyed by query, holds _id
        self._query_cache = defaultdict(OrderedDict)
        self._instance_cache = defaultdict(OrderedDict)  # keyed by _id

    def _normalize_query(self, query):
        _query = query
        if not isinstance(_query, tuple):
            _query = tuple(sorted(list(_query.items()), key=lambda k: k[0]))
        return _query

    def _model_query(self, cls):
        if hasattr(cls, 'query'):
            return cls.query
        elif hasattr(cls, 'm'):
            return cls.m
        else:
            raise AttributeError(
                '%s has neither "query" nor "m" attribute' % cls)

    def get(self, cls, query):
        _query = self._normalize_query(query)
        self._touch(cls, _query)
        if _query not in self._query_cache[cls]:
            val = self._model_query(cls).get(**query)
            self.set(cls, _query, val)
            return val
        _id = self._query_cache[cls][_query]
        if _id is None:
            return None
        if _id not in self._instance_cache[cls]:
            val = self._model_query(cls).get(**query)
            self.set(cls, _query, val)
            return val
        return self._instance_cache[cls][_id]

    def set(self, cls, query, val):
        _query = self._normalize_query(query)
        if val is not None:
            _id = getattr(val, '_model_cache_id',
                          getattr(val, '_id',
                                  self._query_cache[cls].get(_query,
                                                             None)))
            if _id is None:
                _id = val._model_cache_id = bson.ObjectId()
            self._query_cache[cls][_query] = _id
            self._instance_cache[cls][_id] = val
        else:
            self._query_cache[cls][_query] = None
        self._touch(cls, _query)
        self._check_sizes(cls)

    def _touch(self, cls, query):
        '''
        Keep track of insertion order, prevent duplicates,
        and expire from the cache in a FIFO manner.
        '''
        _query = self._normalize_query(query)
        if _query not in self._query_cache[cls]:
            return
        _id = self._query_cache[cls].pop(_query)
        self._query_cache[cls][_query] = _id

        if _id not in self._instance_cache[cls]:
            return
        val = self._instance_cache[cls].pop(_id)
        self._instance_cache[cls][_id] = val

    def _check_sizes(self, cls):
        if self.num_queries(cls) > self._max_queries[cls]:
            _id = self._remove_least_recently_used(self._query_cache[cls])
            if _id in self._instance_cache[cls]:
                instance = self._instance_cache[cls][_id]
                self._try_flush(instance, expunge=False)
        if self.num_instances(cls) > self._max_instances[cls]:
            instance = self._remove_least_recently_used(
                self._instance_cache[cls])
            self._try_flush(instance, expunge=True)

    def _try_flush(self, instance, expunge=False):
        try:
            inst_session = session(instance)
        except AttributeError:
            inst_session = None
        if inst_session:
            inst_session.flush(instance)
            if expunge:
                inst_session.expunge(instance)

    def _remove_least_recently_used(self, cache):
        # last-used (most-recently-used) is last in cache, so take first
        key, val = cache.popitem(last=False)
        return val

    def num_queries(self, cls=None):
        if cls is None:
            return sum(len(c) for c in self._query_cache.values())
        else:
            return len(self._query_cache[cls])

    def num_instances(self, cls=None):
        if cls is None:
            return sum(len(c) for c in self._instance_cache.values())
        else:
            return len(self._instance_cache[cls])

    def instance_ids(self, cls):
        return list(self._instance_cache[cls].keys())

    def batch_load(self, cls, query, attrs=None):
        '''
        Load multiple results given a query.

        Optionally takes a list of attribute names to use
        as the cache key.  If not given, uses the keys of
        the given query.
        '''
        if attrs is None:
            attrs = list(query.keys())
        for result in self._model_query(cls).find(query):
            keys = {a: getattr(result, a) for a in attrs}
            self.set(cls, keys, result)


class GitLikeTree:

    '''
    A tree node similar to that which is used in git

    :var dict blobs: files at this level of the tree.  name => oid
    :var dict trees: subtrees (child dirs).  name => GitLikeTree
    '''

    def __init__(self):
        self.blobs = {}  # blobs[name] = oid
        self.trees = defaultdict(GitLikeTree)  # trees[name] = GitLikeTree()
        self._hex = None

    def get_tree(self, path):
        path = h.really_unicode(path)
        if path.startswith('/'):
            path = path[1:]
        if not path:
            return self
        cur = self
        for part in path.split('/'):
            cur = cur.trees[part]
        return cur

    def get_blob(self, path):
        path = h.really_unicode(path)
        if path.startswith('/'):
            path = path[1:]
        path_parts = path.split('/')
        dirpath, last = path_parts[:-1], path_parts[-1]
        cur = self
        for part in dirpath:
            cur = cur.trees[part]
        return cur.blobs[last]

    def set_blob(self, path, oid):
        path = h.really_unicode(path)
        if path.startswith('/'):
            path = path[1:]
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
            sha_obj = sha1(b'tree\n' + six.ensure_binary(repr(self)))
            self._hex = sha_obj.hexdigest()
        return self._hex

    def __repr__(self):
        # this can't change, is used in hex() above
        lines = [f't {t.hex()} {h.really_unicode(name)}'
                 for name, t in self.trees.items()]
        lines += [f'b {oid} {h.really_unicode(name)}'
                  for name, oid in self.blobs.items()]
        return six.ensure_str('\n'.join(sorted(lines)))

    def __str__(self):
        return self.pretty_tree(recurse=False)

    def pretty_tree(self, indent=0, recurse=True, show_id=True):
        '''For debugging, show a nice tree representation'''
        lines = [' ' * indent + 't %s %s' %
                 (name, '\n' + t.unicode_full_tree(indent + 2, show_id=show_id)
                  if recurse else t.hex())
                 for name, t in sorted(self.trees.items())]
        lines += [' ' * indent + 'b {} {}'.format(name, oid if show_id else '')
                  for name, oid in sorted(self.blobs.items())]
        output = h.really_unicode('\n'.join(lines))
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
    for nid, parents in list(graph.items()):
        if not parents:
            graph.pop(nid)
            roots.append(nid)
        for p_nid in parents:
            children[p_nid].append(nid)
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
    command = [zipbin, '-y', '-q', '-r', zipfile, source_fn.encode('utf-8')]
    if exclude:
        command += ['-x', exclude]
    p = Popen(command, cwd=working_dir, stdout=PIPE, stderr=PIPE)
    stdout, stderr = p.communicate()
    if p.returncode != 0:
        raise Exception(
            "Command: {} returned non-zero exit code {}\n"
            "STDOUT: {}\n"
            "STDERR: {}".format(command, p.returncode, stdout, stderr))


Mapper.compile_all()
