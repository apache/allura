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
import re
import sys
import logging
from hashlib import sha1
from itertools import chain
from datetime import datetime
from collections import defaultdict, OrderedDict
from difflib import SequenceMatcher, unified_diff
import bson

from pylons import tmpl_context as c
import pymongo.errors

from ming import Field, collection, Index
from ming import schema as S
from ming.base import Object
from ming.utils import LazyProperty
from ming.orm import mapper, session

from allura.lib import utils
from allura.lib import helpers as h
from allura.lib.security import has_access

from .auth import User
from .project import AppConfig, Project
from .session import main_doc_session, project_doc_session
from .session import repository_orm_session
from .timeline import ActivityObject

log = logging.getLogger(__name__)

# Some schema types
SUser = dict(name=str, email=str, date=datetime)
SObjType=S.OneOf('blob', 'tree', 'submodule')

# Used for when we're going to batch queries using $in
QSIZE = 100
README_RE = re.compile('^README(\.[^.]*)?$', re.IGNORECASE)
VIEWABLE_EXTENSIONS = ['.php','.py','.js','.java','.html','.htm','.yaml','.sh',
    '.rb','.phtml','.txt','.bat','.ps1','.xhtml','.css','.cfm','.jsp','.jspx',
    '.pl','.php4','.php3','.rhtml','.svg','.markdown','.json','.ini','.tcl','.vbs','.xsl']
PYPELINE_EXTENSIONS = utils.MARKDOWN_EXTENSIONS + ['.rst']

DIFF_SIMILARITY_THRESHOLD = .5  # used for determining file renames

# Basic commit information
# One of these for each commit in the physical repo on disk. The _id is the
# hexsha of the commit (for Git and Hg).
CommitDoc = collection(
    'repo_ci', main_doc_session,
    Field('_id', str),
    Field('tree_id', str),
    Field('committed', SUser),
    Field('authored', SUser),
    Field('message', str),
    Field('parent_ids', [str], index=True),
    Field('child_ids', [str], index=True),
    Field('repo_ids', [ S.ObjectId() ], index=True))

# Basic tree information (also see TreesDoc)
TreeDoc = collection(
    'repo_tree', main_doc_session,
    Field('_id', str),
    Field('tree_ids', [dict(name=str, id=str)]),
    Field('blob_ids', [dict(name=str, id=str)]),
    Field('other_ids', [dict(name=str, id=str, type=SObjType)]))

LastCommitDoc_old = collection(
    'repo_last_commit', project_doc_session,
    Field('_id', str),
    Field('object_id', str, index=True),
    Field('name', str),
    Field('commit_info', dict(
        id=str,
        date=datetime,
        author=str,
        author_email=str,
        author_url=str,
        shortlink=str,
        summary=str)))

# Information about the last commit to touch a tree
LastCommitDoc = collection(
    'repo_last_commit', main_doc_session,
    Field('_id', S.ObjectId()),
    Field('commit_id', str),
    Field('path', str),
    Index('commit_id', 'path'),
    Field('entries', [dict(
        name=str,
        commit_id=str)]))

# List of all trees contained within a commit
# TreesDoc._id = CommitDoc._id
# TreesDoc.tree_ids = [ TreeDoc._id, ... ]
TreesDoc = collection(
    'repo_trees', main_doc_session,
    Field('_id', str),
    Field('tree_ids', [str]))

# Information about which things were added/removed in  commit
# DiffInfoDoc._id = CommitDoc._id
DiffInfoDoc = collection(
    'repo_diffinfo', main_doc_session,
    Field('_id', str),
    Field(
        'differences',
        [ dict(name=str, lhs_id=str, rhs_id=str)]))

# List of commit runs (a run is a linear series of single-parent commits)
# CommitRunDoc.commit_ids = [ CommitDoc._id, ... ]
CommitRunDoc = collection(
    'repo_commitrun', main_doc_session,
    Field('_id', str),
    Field('parent_commit_ids', [str], index=True),
    Field('commit_ids', [str], index=True),
    Field('commit_times', [datetime]))

class RepoObject(object):

    def __repr__(self): # pragma no cover
        return '<%s %s>' % (
            self.__class__.__name__, self._id)

    def primary(self):
        return self

    def index_id(self):
        '''Globally unique artifact identifier.  Used for
        SOLR ID, shortlinks, and maybe elsewhere
        '''
        id = '%s.%s#%s' % (
            self.__class__.__module__,
            self.__class__.__name__,
            self._id)
        return id.replace('.', '/')

    @classmethod
    def upsert(cls, id, **kwargs):
        isnew = False
        r = cls.query.get(_id=id)
        if r is not None: return r, isnew
        try:
            r = cls(_id=id, **kwargs)
            session(r).flush(r)
            isnew = True
        except pymongo.errors.DuplicateKeyError: # pragma no cover
            session(r).expunge(r)
            r = cls.query.get(_id=id)
        return r, isnew

class Commit(RepoObject, ActivityObject):
    type_s = 'Commit'
    # Ephemeral attrs
    repo=None

    @property
    def activity_name(self):
        return self.shorthand_id()

    @property
    def activity_extras(self):
        d = ActivityObject.activity_extras.fget(self)
        d.update(summary=self.summary)
        if self.repo:
            d.update(app_config_id=self.repo.app.config._id)
        return d

    def has_activity_access(self, perm, user, activity):
        """Check access against the original app.

        """
        app_config_id = activity.obj.activity_extras.get('app_config_id')
        if app_config_id:
            app_config = AppConfig.query.get(_id=app_config_id)
            if app_config:
                project = Project.query.get(_id=app_config.project_id)
                app = app_config.load()(project, app_config)
                return has_access(app, perm, user, project)
        return True

    def set_context(self, repo):
        self.repo = repo

    @LazyProperty
    def author_url(self):
        u = User.by_email_address(self.authored.email)
        if u: return u.url()

    @LazyProperty
    def committer_url(self):
        u = User.by_email_address(self.committed.email)
        if u: return u.url()

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
        message = h.really_unicode(self.message)
        first_line = message.split('\n')[0]
        return h.text.truncate(first_line, 50)

    def shorthand_id(self):
        if self.repo is None: self.repo = self.guess_repo()
        if self.repo is None: return repr(self)
        return self.repo.shorthand_for_commit(self._id)

    @LazyProperty
    def symbolic_ids(self):
        return self.repo.symbolics_for_commit(self)

    def get_parent(self, index=0):
        '''Get the parent of this commit.

        If there is no parent commit, or if an invalid index is given,
        returns None.
        '''
        try:
            cache = getattr(c, 'model_cache', '') or ModelCache()
            ci = cache.get(Commit, dict(_id=self.parent_ids[index]))
            if not ci:
                return None
            ci.set_context(self.repo)
            return ci
        except IndexError as e:
            return None

    def climb_commit_tree(self, predicate=None):
        '''
        Returns a generator that walks up the commit tree along
        the first-parent ancestory, starting with this commit,
        optionally filtering by a predicate.'''
        ancestor = self
        while ancestor:
            if predicate is None or predicate(ancestor):
                yield ancestor
            ancestor = ancestor.get_parent()

    def url(self):
        if self.repo is None: self.repo = self.guess_repo()
        if self.repo is None: return '#'
        return self.repo.url_for_commit(self)

    def guess_repo(self):
        import traceback
        log.error('guess_repo: should not be called: %s' % ''.join(traceback.format_stack()))
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

        By default this method returns shorthand_id(). Subclasses should
        override this method to provide more descriptive link text.
        '''
        return self.shorthand_id()

    def context(self):
        result = dict(prev=None, next=None)
        if self.parent_ids:
            result['prev'] = self.query.find(dict(_id={'$in': self.parent_ids })).all()
            for ci in result['prev']:
                ci.set_context(self.repo)
        if self.child_ids:
            result['next'] = self.query.find(dict(_id={'$in': self.child_ids })).all()
            for ci in result['next']:
                ci.set_context(self.repo)
        return result

    @LazyProperty
    def diffs(self):
        return self.paged_diffs()

    def paged_diffs(self, start=0, end=None):
        di = DiffInfoDoc.m.get(_id=self._id)
        if di is None:
            return Object(added=[], removed=[], changed=[], copied=[], total=0)
        added = []
        removed = []
        changed = []
        copied = []
        for change in di.differences[start:end]:
            if change.rhs_id is None:
                removed.append(change.name)
            elif change.lhs_id is None:
                added.append(change.name)
            else:
                changed.append(change.name)
        copied = self._diffs_copied(added, removed)
        return Object(
            added=added, removed=removed,
            changed=changed, copied=copied,
            total=len(di.differences))

    def _diffs_copied(self, added, removed):
        '''Return list with file renames diffs.

        Will change `added` and `removed` lists also.
        '''
        def _blobs_similarity(removed_blob, added):
            best = dict(ratio=0, name='', blob=None)
            for added_name in added:
                added_blob = self.tree.get_obj_by_path(added_name)
                if not isinstance(added_blob, Blob):
                    continue
                diff = SequenceMatcher(None, removed_blob.text,
                                       added_blob.text)
                ratio = diff.quick_ratio()
                if ratio > best['ratio']:
                    best['ratio'] = ratio
                    best['name'] = added_name
                    best['blob'] = added_blob

                if ratio == 1:
                    break  # we'll won't find better similarity than 100% :)

            if best['ratio'] > DIFF_SIMILARITY_THRESHOLD:
                diff = ''
                if best['ratio'] < 1:
                    added_blob = best['blob']
                    rpath = ('a' + removed_blob.path()).encode('utf-8')
                    apath = ('b' + added_blob.path()).encode('utf-8')
                    diff = ''.join(unified_diff(list(removed_blob),
                                                list(added_blob),
                                                rpath, apath))
                return dict(new=best['name'],
                            ratio=best['ratio'], diff=diff)

        def _trees_similarity(removed_tree, added):
            for added_name in added:
                added_tree = self.tree.get_obj_by_path(added_name)
                if not isinstance(added_tree, Tree):
                    continue
                if removed_tree._id == added_tree._id:
                    return dict(new=added_name,
                                ratio=1, diff='')

        if not removed:
            return []
        copied = []
        prev_commit = self.get_parent()
        for removed_name in removed[:]:
            removed_blob = prev_commit.tree.get_obj_by_path(removed_name)
            rename_info = None
            if isinstance(removed_blob, Blob):
                rename_info = _blobs_similarity(removed_blob, added)
            elif isinstance(removed_blob, Tree):
                rename_info = _trees_similarity(removed_blob, added)
            if rename_info is not None:
                rename_info['old'] = removed_name
                copied.append(rename_info)
                removed.remove(rename_info['old'])
                added.remove(rename_info['new'])
        return copied

    def get_path(self, path, create=True):
        path = path.lstrip('/')
        parts = path.split('/')
        cur = self.get_tree(create)
        if cur is not None:
            for part in parts:
                if part != '':
                    cur = cur[part]
        return cur

    def has_path(self, path):
        try:
            self.get_path(path)
            return True
        except KeyError:
            return False

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
        diff_info = DiffInfoDoc.m.get(_id=self._id)
        diffs = set()
        if diff_info:
            for d in diff_info.differences:
                node = d.name.strip('/')
                diffs.add(node)
                node_path = os.path.dirname(node)
                while node_path:
                    diffs.add(node_path)
                    node_path = os.path.dirname(node_path)
                diffs.add('')  # include '/' if there are any changes
        return diffs

    @LazyProperty
    def added_paths(self):
        '''
        Returns a list of paths added in this commit.
        Leading and trailing slashes are removed, and
        the list is complete, meaning that if a directory
        with subdirectories is added, all of the child
        paths are included (this relies on the DiffInfoDoc
        being complete).

        Example:

            If the directory /foo/bar/ is added in the commit
            which contains a subdirectory /foo/bar/baz/ with
            the file /foo/bar/baz/qux.txt, this would return:
            ['foo/bar', 'foo/bar/baz', 'foo/bar/baz/qux.txt']
        '''
        diff_info = DiffInfoDoc.m.get(_id=self._id)
        diffs = set()
        if diff_info:
            for d in diff_info.differences:
                if d.lhs_id is None:
                    diffs.add(d.name.strip('/'))
        return diffs

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

class Tree(RepoObject):
    # Ephemeral attrs
    repo=None
    commit=None
    parent=None
    name=None

    def compute_hash(self):
        '''Compute a hash based on the contents of the tree.  Note that this
        hash does not necessarily correspond to any actual DVCS hash.
        '''
        lines = (
            [ 'tree' + x.name + x.id for x in self.tree_ids ]
            + [ 'blob' + x.name + x.id for x in self.blob_ids ]
            + [ x.type + x.name + x.id for x in self.other_ids ])
        sha_obj = sha1()
        for line in sorted(lines):
            sha_obj.update(line)
        return sha_obj.hexdigest()

    def __getitem__(self, name):
        cache = getattr(c, 'model_cache', '') or ModelCache()
        obj = self.by_name[name]
        if obj['type'] == 'blob':
            return Blob(self, name, obj['id'])
        if obj['type'] == 'submodule':
            log.info('Skipping submodule "%s"' % name)
            raise KeyError, name
        obj = cache.get(Tree, dict(_id=obj['id']))
        if obj is None:
            oid = self.repo.compute_tree_new(self.commit, self.path() + name + '/')
            obj = cache.get(Tree, dict(_id=oid))
        if obj is None: raise KeyError, name
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
        each node.  Eventually, ls_old can be removed and this can be
        replaced with the following:

            return self._lcd_map(LastCommit.get(self))
        '''
        # look for existing new format first
        last_commit = LastCommit.get(self, create=False)
        if last_commit:
            return self._lcd_map(last_commit)
        # otherwise, try old format
        old_style_results = self.ls_old()
        if old_style_results:
            log.info('Using old-style results from ls_old()')
            return old_style_results
        # finally, use the new implentation that auto-vivifies
        last_commit = LastCommit.get(self, create=True)
        # ensure that the LCD is saved, even if
        # there is an error later in the request
        if last_commit:
            session(last_commit).flush(last_commit)
            return self._lcd_map(last_commit)
        else:
            return []

    def _lcd_map(self, lcd):
        if lcd is None:
            return []
        commit_ids = [e.commit_id for e in lcd.entries]
        commits = list(Commit.query.find(dict(_id={'$in': commit_ids})))
        for commit in commits:
            commit.set_context(self.repo)
        commit_infos = {c._id: c.info for c in commits}
        by_name = lambda n: n.name
        tree_names = sorted([n.name for n in self.tree_ids])
        blob_names = sorted([n.name for n in chain(self.blob_ids, self.other_ids)])

        results = []
        for type, names in (('DIR', tree_names), ('BLOB', blob_names)):
            for name in names:
                commit_info = commit_infos.get(lcd.by_name.get(name))
                if not commit_info:
                    commit_info = defaultdict(str)
                elif 'id' in commit_info:
                    commit_info['href'] = self.repo.url_for_commit(commit_info['id'])
                results.append(dict(
                        kind=type,
                        name=name,
                        href=name,
                        last_commit=dict(
                                author=commit_info['author'],
                                author_email=commit_info['author_email'],
                                author_url=commit_info['author_url'],
                                date=commit_info.get('date'),
                                href=commit_info.get('href',''),
                                shortlink=commit_info['shortlink'],
                                summary=commit_info['summary'],
                            ),
                    ))
        return results

    def ls_old(self):
        # Load last commit info
        id_re = re.compile("^{0}:{1}:".format(
            self.repo._id,
            re.escape(h.really_unicode(self.path()).encode('utf-8'))))
        lc_index = dict(
            (lc.name, lc.commit_info)
            for lc in LastCommitDoc_old.m.find(dict(_id=id_re)))

        # FIXME: Temporarily fall back to old, semi-broken lookup behavior until refresh is done
        oids = [ x.id for x in chain(self.tree_ids, self.blob_ids, self.other_ids) ]
        id_re = re.compile("^{0}:".format(self.repo._id))
        lc_index.update(dict(
            (lc.object_id, lc.commit_info)
            for lc in LastCommitDoc_old.m.find(dict(_id=id_re, object_id={'$in': oids}))))
        # /FIXME

        if not lc_index:
            # allow fallback to new method instead
            # of showing a bunch of Nones
            return []

        results = []
        def _get_last_commit(name, oid):
            lc = lc_index.get(name, lc_index.get(oid, None))
            if lc is None:
                lc = dict(
                    author=None,
                    author_email=None,
                    author_url=None,
                    date=None,
                    id=None,
                    href=None,
                    shortlink=None,
                    summary=None)
            if 'href' not in lc:
                lc['href'] = self.repo.url_for_commit(lc['id'])
            return lc
        for x in sorted(self.tree_ids, key=lambda x:x.name):
            results.append(dict(
                    kind='DIR',
                    name=x.name,
                    href=x.name + '/',
                    last_commit=_get_last_commit(x.name, x.id)))
        for x in sorted(self.blob_ids, key=lambda x:x.name):
            results.append(dict(
                    kind='FILE',
                    name=x.name,
                    href=x.name,
                    last_commit=_get_last_commit(x.name, x.id)))
        for x in sorted(self.other_ids, key=lambda x:x.name):
            results.append(dict(
                    kind=x.type,
                    name=x.name,
                    href=None,
                    last_commit=_get_last_commit(x.name, x.id)))
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

class Blob(object):
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
    def prev_commit(self):
        pcid = LastCommit._prev_commit_id(self.commit, self.path().strip('/'))
        if pcid:
            return self.repo.commit(pcid)
        return None

    @LazyProperty
    def next_commit(self):
        try:
            path = self.path()
            cur = self.commit
            next = cur.context()['next']
            while next:
                cur = next[0]
                next = cur.context()['next']
                other_blob = cur.get_path(path, create=False)
                if other_blob is None or other_blob._id != self._id:
                    return cur
        except:
            log.exception('Lookup next_commit')
            return None

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

    @property
    def has_html_view(self):
        if (self.content_type.startswith('text/') or
            self.extension in VIEWABLE_EXTENSIONS or
            self.extension in PYPELINE_EXTENSIONS or
            self.extension in self.repo._additional_viewable_extensions or
            utils.is_text_file(self.text)):
            return True
        return False

    @property
    def has_image_view(self):
        return self.content_type.startswith('image/')

    def context(self):
        path = self.path()
        prev = self.prev_commit
        next = self.next_commit
        if prev is not None:
            try:
                prev = prev.get_path(path, create=False)
            except KeyError as e:
                prev = None
        if next is not None:
            try:
                next = next.get_path(path, create=False)
            except KeyError as e:
                next = None
        return dict(
            prev=prev,
            next=next)

    def open(self):
        return self.repo.open_blob(self)

    def __iter__(self):
        return iter(self.open())

    @LazyProperty
    def size(self):
        return self.repo.blob_size(self)

    @LazyProperty
    def text(self):
        return self.open().read()

    @classmethod
    def diff(cls, v0, v1):
        differ = SequenceMatcher(v0, v1)
        return differ.get_opcodes()

class LastCommit(RepoObject):
    def __repr__(self):
        return '<LastCommit /%s %s>' % (self.path, self.commit_id)

    @classmethod
    def _last_commit_id(cls, commit, path):
        try:
            rev = commit.repo.log(commit._id, path, id_only=True).next()
            return commit.repo.rev_to_commit_id(rev)
        except StopIteration:
            log.error('Tree node not recognized by SCM: %s @ %s', path, commit._id)
            return commit._id

    @classmethod
    def _prev_commit_id(cls, commit, path):
        if not commit.parent_ids or path in commit.added_paths:
            return None  # new paths by definition have no previous LCD
        lcid_cache = getattr(c, 'lcid_cache', '')
        if lcid_cache != '' and path in lcid_cache:
            return lcid_cache[path]
        try:
            log_iter = commit.repo.log(commit._id, path, id_only=True)
            log_iter.next()
            rev = log_iter.next()
            return commit.repo.rev_to_commit_id(rev)
        except StopIteration:
            return None

    @classmethod
    def get(cls, tree, create=True):
        '''Find or build the LastCommitDoc for the given tree.'''
        cache = getattr(c, 'model_cache', '') or ModelCache()
        path = tree.path().strip('/')
        last_commit_id = cls._last_commit_id(tree.commit, path)
        lcd = cache.get(cls, {'path': path, 'commit_id': last_commit_id})
        if lcd is None and create:
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
            prev_lcd = model_cache.get(cls, {'path': path, 'commit_id': prev_lcd_cid})
        entries = {}
        nodes = set([node.name for node in chain(tree.tree_ids, tree.blob_ids, tree.other_ids)])
        changed = set([node for node in nodes if os.path.join(path, node) in tree.commit.changed_paths])
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
            entries = {os.path.basename(path):commit_id for path,commit_id in entries.iteritems()}
        # update with the nodes changed in this tree's commit
        entries.update({node: tree.commit._id for node in changed})
        # convert to a list of dicts, since mongo doesn't handle arbitrary keys well (i.e., . and $ not allowed)
        entries = [{'name':name, 'commit_id':value} for name,value in entries.iteritems()]
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

mapper(Commit, CommitDoc, repository_orm_session)
mapper(Tree, TreeDoc, repository_orm_session)
mapper(LastCommit, LastCommitDoc, repository_orm_session)


class ModelCache(object):
    '''
    Cache model instances based on query params passed to get.
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
        self._max_instances = defaultdict(lambda:max_instances_default)
        self._max_queries = defaultdict(lambda:max_queries_default)
        if hasattr(max_instances, 'items'):
            self._max_instances.update(max_instances)
        if hasattr(max_queries, 'items'):
            self._max_queries.update(max_queries)

        self._query_cache = defaultdict(OrderedDict)  # keyed by query, holds _id
        self._instance_cache = defaultdict(OrderedDict)  # keyed by _id
        self._synthetic_ids = defaultdict(set)
        self._synthetic_id_queries = defaultdict(set)

    def _normalize_query(self, query):
        _query = query
        if not isinstance(_query, tuple):
            _query = tuple(sorted(_query.items(), key=lambda k: k[0]))
        return _query

    def _model_query(self, cls):
        if hasattr(cls, 'query'):
            return cls.query
        elif hasattr(cls, 'm'):
            return cls.m
        else:
            raise AttributeError('%s has neither "query" nor "m" attribute' % cls)

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
                self._synthetic_ids[cls].add(_id)
            if _id in self._synthetic_ids:
                self._synthetic_id_queries[cls].add(_query)
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
            instance = self._remove_least_recently_used(self._instance_cache[cls])
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

    def expire_new_instances(self, cls):
        '''
        Expire any instances that were "new" or had no _id value.

        If a lot of new instances of a class are being created, it's possible
        for a query to pull a copy from mongo when a copy keyed by the synthetic
        ID is still in the cache, potentially causing de-sync between the copies
        leading to one with missing data overwriting the other.  Clear new
        instances out of the cache relatively frequently (depending on the query
        and instance cache sizes) to avoid this.
        '''
        for _query in self._synthetic_id_queries[cls]:
            self._query_cache[cls].pop(_query)
        self._synthetic_id_queries[cls] = set()
        for _id in self._synthetic_ids[cls]:
            instance = self._instance_cache[cls].pop(_id)
            self._try_flush(instance, expunge=True)
        self._synthetic_ids[cls] = set()

    def num_queries(self, cls=None):
        if cls is None:
            return sum([len(c) for c in self._query_cache.values()])
        else:
            return len(self._query_cache[cls])

    def num_instances(self, cls=None):
        if cls is None:
            return sum([len(c) for c in self._instance_cache.values()])
        else:
            return len(self._instance_cache[cls])

    def instance_ids(self, cls):
        return self._instance_cache[cls].keys()

    def batch_load(self, cls, query, attrs=None):
        '''
        Load multiple results given a query.

        Optionally takes a list of attribute names to use
        as the cache key.  If not given, uses the keys of
        the given query.
        '''
        if attrs is None:
            attrs = query.keys()
        for result in self._model_query(cls).find(query):
            keys = {a: getattr(result, a) for a in attrs}
            self.set(cls, keys, result)
