import os
import shutil
import string
import logging
import random
from collections import namedtuple
from datetime import datetime

import tg
import git
from pymongo.errors import DuplicateKeyError

from ming.base import Object
from ming.orm import Mapper, session, mapper
from ming.utils import LazyProperty

from allura.lib import helpers as h
from allura.lib import utils
from allura import model as M

log = logging.getLogger(__name__)

class Repository(M.Repository):
    tool_name='Git'
    repo_id='git'
    type_s='Git Repository'
    class __mongometa__:
        name='git-repository'

    @LazyProperty
    def _impl(self):
        return GitImplementation(self)

    def suggested_clone_dest_path(self):
        return super(Repository, self).suggested_clone_dest_path()[:-4]

    def clone_url(self, category, username=''):
        return super(Repository, self).clone_url(category, username)[:-4]

    def merge_command(self, merge_request):
        '''Return the command to merge a given commit to a given target branch'''
        return 'git checkout %s\ngit fetch %s\ngit merge %s' % (
            merge_request.target_branch,
            merge_request.downstream_repo_url,
            merge_request.downstream.commit_id,
        )

class GitImplementation(M.RepositoryImplementation):
    post_receive_template = string.Template(
        '#!/bin/bash\n'
        'curl -s $url\n')

    def __init__(self, repo):
        self._repo = repo

    @LazyProperty
    def _git(self):
        try:
            return git.Repo(self._repo.full_fs_path)
        except (git.exc.NoSuchPathError, git.exc.InvalidGitRepositoryError), err:
            log.error('Problem looking up repo: %r', err)
            return None

    def init(self):
        fullname = self._setup_paths()
        log.info('git init %s', fullname)
        if os.path.exists(fullname):
            shutil.rmtree(fullname)
        repo = git.Repo.init(
            path=fullname,
            mkdir=True,
            quiet=True,
            bare=True,
            shared='all')
        self.__dict__['_git'] = repo
        self._setup_special_files()
        self._repo.status = 'ready'

    def clone_from(self, source_url):
        '''Initialize a repo as a clone of another'''
        fullname = self._setup_paths(create_repo_dir=False)
        if os.path.exists(fullname):
            shutil.rmtree(fullname)
        log.info('Initialize %r as a clone of %s',
                 self._repo, source_url)
        repo = git.Repo.clone_from(
            source_url,
            to_path=fullname,
            bare=True)
        self.__dict__['_git'] = repo
        self._setup_special_files()
        self._repo.status = 'analyzing'
        session(self._repo).flush()
        log.info('... %r cloned, analyzing', self._repo)
        self._repo.refresh()
        self._repo.status = 'ready'
        log.info('... %s ready', self._repo)
        session(self._repo).flush()

    def commit(self, rev):
        '''Return a Commit object.  rev can be object_id or a branch/tag name'''
        result = M.Commit.query.get(object_id=rev)
        if result is None:
            # find the id by branch/tag name
            try:
                impl = self._git.rev_parse(str(rev) + '^0')
                result = M.Commit.query.get(object_id=impl.hexsha)
            except Exception:
                url = ''
                try:
                    from tg import request
                    url = ' at ' + request.url
                except:
                    pass
                log.exception('Error with rev_parse(%s)%s' % (str(rev) + '^0', url))
        if result is None: return None
        result.set_context(self._repo)
        return result

    def new_commits(self, all_commits=False):
        commits = list(self._git.iter_commits(topo_order=True))
        if all_commits: return commits
        result = []
        commit_doc = mapper(M.Commit).doc_cls
        sess = M.main_doc_session
        # Chunk our new commits so our queries don't get too big/slow
        for chunk in utils.chunked_iter(commits, self._repo.BATCH_SIZE):
            chunk = list(chunk)
            found_commit_ids = set(
                ci.object_id for ci in sess.find(
                    commit_doc, object_id={'$in': chunk},
                    fields=['_id', 'object_id']))
            result += [ ci for ci in chunk if ci.hexsha not in found_commit_ids ]
        return result

    def commit_parents(self, ci):
        return ci.parents

    def commit_context(self, commit):
        prev_ids = commit.parent_ids
        prev = M.Commit.query.find(dict(
                object_id={'$in':prev_ids})).all()
        next = M.Commit.query.find(dict(
                parent_ids=commit.object_id,
                repositories=self._repo._id)).all()
        for ci in prev + next:
            ci.set_context(self._repo)
        return dict(prev=prev, next=next)

    def refresh_heads(self):
        self._repo.refresh_context.object_cache = ObjectCache()
        self._repo.heads = [
            Object(name=head.name, object_id=head.commit.hexsha)
            for head in self._git.heads
            if head.is_valid() ]
        self._repo.branches = [
            Object(name=head.name, object_id=head.commit.hexsha)
            for head in self._git.branches
            if head.is_valid() ]
        self._repo.repo_tags = [
            Object(name=tag.name, object_id=tag.commit.hexsha)
            for tag in self._git.tags
            if tag.is_valid() ]
        session(self._repo).flush()

    def refresh_commit(self, ci, native_ci):
        ci.tree_id = native_ci.tree.hexsha
        log.info('Refresh commit %s', native_ci)
        # Save commit metadata
        ci.committed = Object(
            name=h.really_unicode(native_ci.committer.name),
            email=h.really_unicode(native_ci.committer.email),
            date=datetime.utcfromtimestamp(
                native_ci.committed_date))
        ci.authored=Object(
            name=h.really_unicode(native_ci.author.name),
            email=h.really_unicode(native_ci.author.email),
            date=datetime.utcfromtimestamp(native_ci.authored_date))
        ci.message=h.really_unicode(native_ci.message or '')
        ci.parent_ids=[ p.hexsha for p in native_ci.parents ]
        if ci.tree_id in self._repo.refresh_context.seen_oids: return
        self._repo.refresh_context.seen_oids.add(native_ci.tree.hexsha)
        root_entry = self._repo.refresh_context.object_cache[native_ci.tree]
        self._build_manifest(native_ci)
        self.refresh_tree(root_entry)

    def _build_manifest(self, native_ci):
        '''Build the manifest for this commit (mapof all paths to trees/blobs)

        Along the way, also build & save the Manifests for sub-trees
        '''
        cache = self._repo.refresh_context.object_cache
        maxsize = int(self._repo.refresh_context.max_manifest_size * 1.1)
        cache.trim(maxsize)
        log.info('Cache has %d/%d items', len(cache), maxsize)
        def _object_ids(name, obj, entry=None):
            '''Iterate over dict(name, oid) object ids that are part of obj'''
            if entry is None:
                entry = cache[obj]
            if entry.entries is None:
                yield Object(name=name or '/', object_id=obj.hexsha)
            else:
                yield Object(name=name or '/', object_id=obj.hexsha)
                for e_name, e in entry.entries:
                    for x in _object_ids(name + '/' + e_name, e.obj, e):
                        yield x
        result =M.Manifest.from_iter(
            native_ci.hexsha,
            _object_ids('', native_ci.tree))
        manifest_size = sum(len(m.object_ids) for m in result)
        self._repo.refresh_context.max_manifest_size = max(
            self._repo.refresh_context.max_manifest_size, manifest_size)
        return result

    def object_id(self, obj):
        return obj.hexsha

    def log(self, object_id, skip, count):
        return list(self._git.iter_commits(
                object_id,
                skip=skip,
                max_count=count,
                topo_order=True))

    def open_blob(self, blob):
        return _OpenedGitBlob(
            self._object(blob.object_id).data_stream)

    def _setup_hooks(self):
        'Set up the git post-commit hook'
        text = self.post_receive_template.substitute(
            url=tg.config.get('base_url', 'http://localhost:8080')
            + '/auth/refresh_repo' + self._repo.url())
        fn = os.path.join(self._repo.fs_path, self._repo.name, 'hooks', 'post-receive')
        with open(fn, 'w') as fp:
            fp.write(text)
        os.chmod(fn, 0755)

    def refresh_tree(self, entry):
        tree_doc_cls = mapper(M.Tree).doc_cls
        blob_doc_cls = mapper(M.Tree).doc_cls
        tree = tree_doc_cls(dict(
            type='tree',
            object_id=entry.oid,
            object_ids=[]))
        try:
            M.main_doc_session.insert(tree)
        except DuplicateKeyError:
            return
        tree.object_ids = [
            Object(name=name, object_id=e.oid)
            for (name, e) in entry.entries ]
        M.main_doc_session.save(tree)
        for name, e in entry.entries:
            if e.oid in self._repo.refresh_context.seen_oids: continue
            self._repo.refresh_context.seen_oids.add(e.oid)
            if e.entries is None:
                M.main_doc_session.insert(blob_doc_cls(dict(
                            type='blob', object_id=e.oid)))
            else:
                self.refresh_tree(e)

    def generate_shortlinks(self, ci):
        for link in ci.object_id, ci.object_id[:6]:
            M.Shortlink(
                ref_id=None,
                project_id=ci.project_id,
                app_config_id=ci.app_config_id,
                link=link,
                url=ci.url)

    def _object(self, oid):
        evens = oid[::2]
        odds = oid[1::2]
        binsha = ''
        for e,o in zip(evens, odds):
            binsha += chr(int(e+o, 16))
        return git.Object.new_from_sha(self._git, binsha)

    def symbolics_for_commit(self, commit):
        branch_heads, tags = super(self.__class__, self).symbolics_for_commit(commit)
        containing_branches = self._git.git.branch(contains=commit.object_id)
        containing_branches = [br.strip(' *') for br in containing_branches.split('\n')]
        return containing_branches, tags

class _OpenedGitBlob(object):
    CHUNK_SIZE=4096

    def __init__(self, stream):
        self._stream = stream

    def read(self):
        return self._stream.read()

    def __iter__(self):
        '''
        Yields one line at a time, reading from the stream
        '''
        buffer = ''
        while True:
            # Replenish buffer until we have a line break
            while '\n' not in buffer:
                chars = self._stream.read(self.CHUNK_SIZE)
                if not chars: break
                buffer += chars
            if not buffer: break
            eol = buffer.find('\n')
            if eol == -1:
                # end without \n
                yield buffer
                break
            yield buffer[:eol+1]
            buffer = buffer[eol+1:]

    def close(self):
        pass

class ObjectCache(object):
    Entry = namedtuple('Entry', 'oid obj entries')

    def __init__(self):
        self._data = {}

    def __getitem__(self, obj):
        if obj.hexsha in self._data:
            return self._data[obj.hexsha]
        if obj.type == 'blob':
            r = self._data[obj.hexsha] = self.Entry(
                oid=obj.hexsha, obj=obj, entries=None)
            return r
        elif obj.type == 'tree':
            r = self._data[obj.hexsha] = self.Entry(
                oid=obj.hexsha,
                obj=obj,
                entries=[ (o.name, self[o]) for o in obj ])
            return r

    def __len__(self):
        return len(self._data)

    def by_oid(self, oid):
        return self._data[oid]

    def trim(self, maxsize):
        if len(self._data) > maxsize:
            self._data = dict(random.sample(self._data.items(), int(maxsize * 0.5)))


Mapper.compile_all()
