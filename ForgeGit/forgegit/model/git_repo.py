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

import os
import shutil
import string
import logging
import tempfile
from datetime import datetime
from contextlib import contextmanager
from time import time
import typing

import tg
import git
import gitdb
from tg import tmpl_context as c
from pymongo.errors import DuplicateKeyError
from paste.deploy.converters import asbool
import six

from ming.base import Object
from ming.odm import state, Mapper, session
from ming.odm.base import ObjectState
from ming.utils import LazyProperty

from allura.lib import helpers as h
from allura.model.repository import topological_sort, prefix_paths_union
from allura import model as M

if typing.TYPE_CHECKING:
    from ming.odm.mapper import Query


log = logging.getLogger(__name__)

gitdb.util.mman = gitdb.util.mman.__class__(
    max_open_handles=128)


class GitLibCmdWrapper:

    def __init__(self, client):
        self.client = client

    def __getattr__(self, name):
        return getattr(self.client, name)

    def log(self, *args, **kwargs):
        return self.client.log(*args, **kwargs)


class Repository(M.Repository):
    tool_name = 'Git'
    repo_id = 'git'
    type_s = 'Git Repository'

    class __mongometa__:
        name = 'git-repository'

    query: 'Query[Repository]'

    @LazyProperty
    def _impl(self):
        return GitImplementation(self)

    def suggested_clone_dest_path(self):
        return super().suggested_clone_dest_path()[:-4]

    def clone_url(self, category, username=''):
        clone_url = super().clone_url(category, username)
        if clone_url.endswith('.git'):
            clone_url = clone_url[:-4]
        return clone_url

    def merge_command(self, merge_request):
        '''Return the command to merge a given commit to a given target branch'''
        if merge_request.source_branch:
            fetch_command = 'git fetch {} {}'.format(
                merge_request.downstream_repo.clone_url_first(anon=False, username=c.user.username),
                merge_request.source_branch,
            )
        else:
            fetch_command = (
                'git remote add merge_request {}\n'
                'git fetch merge_request'
            ).format(
                merge_request.downstream_repo.clone_url_first(anon=False, username=c.user.username),
            )
        return 'git checkout {}\n{}\ngit merge {}'.format(
            merge_request.target_branch,
            fetch_command,
            merge_request.downstream.commit_id,
        )

    def can_merge(self, mr):
        """
        Given merge request `mr` determine if it can be merged w/o conflicts.
        """
        g = self._impl._git.git
        # http://stackoverflow.com/a/6283843
        # fetch source branch
        g.fetch(mr.downstream_repo.full_fs_path, mr.source_branch)
        # find merge base
        merge_base = g.merge_base(mr.downstream.commit_id, mr.target_branch)
        # print out merge result, but don't actually touch anything
        merge_tree = g.merge_tree(
            merge_base, mr.target_branch, mr.downstream.commit_id)
        return '+<<<<<<<' not in merge_tree

    def merge(self, mr):
        g = self._impl._git.git
        # can't merge in bare repo, so need to clone
        tmp_path = tempfile.mkdtemp()
        try:
            tmp_repo = git.Repo.clone_from(
                self.full_fs_path,
                to_path=tmp_path,
                shared=True,
                bare=False)
            tmp_repo = GitImplementation(Object(full_fs_path=tmp_path))._git
            tmp_repo.git.fetch('origin', mr.target_branch)
            tmp_repo.git.checkout(mr.target_branch)
            tmp_repo.git.fetch(mr.downstream_repo.full_fs_path, mr.source_branch)
            author = h.really_unicode(c.user.display_name or c.user.username)
            tmp_repo.git.config('user.name', author.encode('utf8'))
            tmp_repo.git.config('user.email', 'allura@localhost')  # a public email alias could be nice here
            msg = 'Merge {} branch {} into {}\n\n{}'.format(
                mr.downstream_repo.url(),
                mr.source_branch,
                mr.target_branch,
                h.absurl(mr.url()))
            tmp_repo.git.merge(mr.downstream.commit_id, '-m', msg)
            tmp_repo.git.push('origin', mr.target_branch)
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)

    def rev_to_commit_id(self, rev):
        return self._impl.rev_parse(rev).hexsha


class GitImplementation(M.RepositoryImplementation):
    post_receive_template = string.Template(
        '#!/bin/bash\n'
        '# The following is required for site integration, do not remove/modify.\n'
        '# Place user hook code in post-receive-user and it will be called from here.\n'
        'curl -s $url\n'
        '\n'
        'DIR="$$(dirname "$${BASH_SOURCE[0]}")"\n'
        'if [ -x $$DIR/post-receive-user ]; then\n'
        '  exec $$DIR/post-receive-user\n'
        'fi')

    def __init__(self, repo):
        self._repo = repo

    @LazyProperty
    def _git(self):
        try:
            _git = git.Repo(self._repo.full_fs_path, odbt=git.GitCmdObjectDB)
            _git.git = GitLibCmdWrapper(_git.git)
            return _git
        except (git.exc.NoSuchPathError, git.exc.InvalidGitRepositoryError) as err:
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
        self._repo.set_status('ready')

    def can_hotcopy(self, source_url):
        enabled = asbool(tg.config.get('scm.git.hotcopy', True))
        is_local = os.path.exists(source_url)
        requested = self._repo.app.config.options.get('hotcopy', False)
        return enabled and is_local and requested

    def clone_from(self, source_url):
        '''Initialize a repo as a clone of another'''
        self._repo.set_status('cloning')
        log.info('Initialize %r as a clone of %s',
                 self._repo, source_url)
        try:
            fullname = self._setup_paths(create_repo_dir=False)
            if os.path.exists(fullname):
                shutil.rmtree(fullname)
            if self.can_hotcopy(source_url):
                shutil.copytree(source_url, fullname)
                post_receive = os.path.join(
                    self._repo.full_fs_path, 'hooks', 'post-receive')
                if os.path.exists(post_receive):
                    os.rename(post_receive, post_receive + '-user')
                repo = git.Repo(fullname)
            else:
                repo = git.Repo.clone_from(
                    source_url,
                    to_path=fullname,
                    bare=True)
            self.__dict__['_git'] = repo
            self._setup_special_files(source_url)
        except Exception:
            self._repo.set_status('ready')
            raise

    def commit(self, rev):
        '''Return a Commit object.  rev can be _id or a branch/tag name'''
        cache = getattr(c, 'model_cache', '') or M.repository.ModelCache()
        result = cache.get(M.repository.Commit, dict(_id=rev))
        if result is None:
            # find the id by branch/tag name
            try:
                impl = self._git.rev_parse(str(rev) + '^0')
                result = cache.get(M.repository.Commit, dict(_id=impl.hexsha))
            except Exception:
                url = ''
                try:
                    from tg import request
                    url = ' at ' + request.url
                except Exception:
                    pass
                log.info(f"couldn't run rev_parse({str(rev) + '^0'}){url}", exc_info=True)
        if result:
            result.set_context(self._repo)
        return result

    def all_commit_ids(self):
        """Yield commit ids, starting with the head(s) of the commit tree and
        ending with the root (first commit).
        """
        if self.is_empty():
            return
        seen = set()
        for ci in self._git.iter_commits(all=True, topo_order=True):
            if ci.binsha in seen:
                continue
            seen.add(ci.binsha)
            yield ci.hexsha

    def new_commits(self, all_commits=False):
        graph = {}

        to_visit = [self._git.commit(rev=hd.object_id) for hd in self.heads]
        while to_visit:
            obj = to_visit.pop()
            if obj.hexsha in graph:
                continue
            if not all_commits:
                # Look up the object
                if M.repository.Commit.query.find(dict(_id=obj.hexsha)).count():
                    graph[obj.hexsha] = set()  # mark as parentless
                    continue
            graph[obj.hexsha] = {p.hexsha for p in obj.parents}
            to_visit += obj.parents
        return list(topological_sort(graph))

    def refresh_commit_info(self, oid, seen, lazy=True):
        from allura.model.repository import CommitDoc
        ci_doc = CommitDoc.m.get(_id=oid)
        if ci_doc and lazy:
            return False
        ci = self._git.rev_parse(oid)
        args = dict(
            tree_id=ci.tree.hexsha,
            committed=Object(
                name=h.really_unicode(ci.committer.name),
                email=h.really_unicode(ci.committer.email),
                date=datetime.utcfromtimestamp(ci.committed_date)),
            authored=Object(
                name=h.really_unicode(ci.author.name),
                email=h.really_unicode(ci.author.email),
                date=datetime.utcfromtimestamp(ci.authored_date)),
            message=h.really_unicode(ci.message or ''),
            child_ids=[],
            parent_ids=[p.hexsha for p in ci.parents])
        if ci_doc:
            ci_doc.update(**args)
            ci_doc.m.save()
        else:
            ci_doc = CommitDoc(dict(args, _id=ci.hexsha))
            try:
                ci_doc.m.insert()
            except DuplicateKeyError:
                if lazy:
                    return False
        self.refresh_tree_info(ci.tree, seen, lazy)
        return True

    def refresh_tree_info(self, tree: git.objects.tree.Tree, seen: set, lazy=True):
        from allura.model.repository import Tree
        if lazy and tree.binsha in seen:
            return
        seen.add(tree.binsha)
        doc = Tree(
            _id=tree.hexsha,
            tree_ids=[],
            blob_ids=[],
            other_ids=[])
        for o in tree:
            if o.type == 'submodule':
                continue
            obj = Object(
                name=h.really_unicode(o.name),
                id=o.hexsha)
            if o.type == 'tree':
                self.refresh_tree_info(o, seen, lazy)
                doc.tree_ids.append(obj)
            elif o.type == 'blob':
                if o.mode == o.link_mode:
                    obj.type = 'symlink'
                    doc.other_ids.append(obj)
                else:
                    doc.blob_ids.append(obj)
            else:
                obj.type = o.type
                doc.other_ids.append(obj)
        # set to 'dirty' to force save() to be used instead of insert() (which errors if doc exists in db already)
        state(doc).status = ObjectState.dirty
        session(doc).flush(doc)
        session(doc).expunge(doc)
        return doc

    def log(self, revs=None, path=None, exclude=None, id_only=True, limit=None, **kw):
        """
        Returns a generator that returns information about commits reachable
        by revs.

        revs can be None or a list or tuple of revisions, each of which
        can be anything parsable by self.commit().  If revs is None, the
        default branch head will be used.

        If path is not None, only commits which modify files under path
        will be included.

        Exclude can be None or a list or tuple of identifiers, each of which
        can be anything parsable by self.commit().  If not None, then any
        revisions reachable by any of the revisions in exclude will not be
        included.

        If id_only is True, returns only the commit ID, otherwise it returns
        detailed information about each commit.
        """
        path = path.strip('/') if path else None
        if exclude is not None:
            revs.extend(['^%s' % e for e in exclude])
        args = ['--follow', '--name-status', revs, '--', path or '.']
        kwargs = {}
        if limit:
            kwargs['n'] = limit
        for ci, refs, renamed in self._iter_commits_with_refs(*args, **kwargs):
            if id_only:
                yield ci.hexsha
            else:
                size = None
                rename_details = {}
                if path:
                    if renamed and renamed['to'] == path:
                        rename_details['path'] = '/' + renamed['from']
                        # get first rev **before** rename
                        _iter = self._git.iter_commits(
                            revs, renamed['from'], max_count=2)
                        prev_rev = list(_iter)[1]
                        rename_details['commit_url'] = self._repo.url_for_commit(
                            prev_rev.hexsha
                        )

                    try:
                        node = ci.tree / path
                        size = node.size if node.type == 'blob' else None
                    except KeyError as e:
                        size = None
                    if rename_details:
                        path = rename_details['path'].strip('/')
                yield {
                    'id': ci.hexsha,
                    'message': h.really_unicode(ci.message or '--none--'),
                    'authored': {
                        'name': h.really_unicode(ci.author.name or '--none--'),
                        'email': h.really_unicode(ci.author.email),
                        'date': datetime.utcfromtimestamp(ci.authored_date),
                    },
                    'committed': {
                        'name': h.really_unicode(ci.committer.name or '--none--'),
                        'email': h.really_unicode(ci.committer.email),
                        'date': datetime.utcfromtimestamp(ci.committed_date),
                    },
                    'refs': refs,
                    'parents': [pci.hexsha for pci in ci.parents],
                    'size': size,
                    'rename_details': rename_details,
                }

    def _iter_commits_with_refs(self, *args, **kwargs):
        """
        A reimplementation of GitPython's iter_commits that includes
        the --decorate option.

        Unfortunately, iter_commits discards the additional info returned
        by adding --decorate, and the ref names are not exposed on the
        commit objects without making an entirely separate call to log.

        Ideally, since we're reimplementing it anyway, we would prefer
        to add all the info we need to the format to avoid the additional
        overhead of the lazy-load of the commit data, but the commit
        message is a problem since it can contain newlines which breaks
        parsing of the log lines (iter_commits can be broken this way,
        too).  This does keep the id_only case fast and the overhead
        of lazy-loading the commit data is probably fine.  But if this
        ends up being a bottleneck, that would be one possibile
        optimization.

        Renaming
        Detection of renaming can be implemented using diff with parent
        with create_path=True. But taking diffs is slow. That's why
        --name-status is added to log.
        Then log returns something like this:
            <commit hash>x00 <refs>
            \n # empty line
            R100 <renamed from path> <renamed to path> # when rename happens
            A\t<some path> # other cases
            D\t<some path> # other cases
            etc
        """
        proc = self._git.git.log(*args,
                                 format='%H%x00%d', as_process=True, **kwargs)
        stream = proc.stdout
        commit_lines = []
        while True:
            line = six.ensure_text(stream.readline())
            if '\x00' in line or not(len(line)):
                # hash line read, need to yield previous commit
                # first, cleaning lines a bit
                commit_lines = [
                    ln.strip('\n ').replace('\t', ' ')
                    for ln in commit_lines if ln.strip('\n ')
                ]
                if commit_lines:
                    hexsha, decoration = commit_lines[0].split('\x00')
                    if decoration:
                        # "->" replacement is because git 2.4 introduced "HEAD -> master" syntax
                        refs = decoration.strip(' ()').replace(' -> ', ', ').split(', ')
                    else:
                        refs = []
                    tag_prefix = 'tag: '  # introduced in git 1.8.3
                    for i, ref in enumerate(refs):
                        if ref.startswith(tag_prefix):
                            refs[i] = ref[len(tag_prefix):]
                    refs.sort()
                    renamed = {}
                    # merge commits don't have any --name-status output
                    if len(commit_lines) > 1:
                        name_stat_parts = commit_lines[1].split(' ')
                        if name_stat_parts[0] == 'R100':
                            renamed['from'] = name_stat_parts[1]
                            renamed['to'] = name_stat_parts[2]
                    yield (git.Commit(self._git, gitdb.util.hex_to_bin(hexsha)), refs, renamed)
                if not(len(line)):
                    # if all lines have been read
                    break
                commit_lines = [line]
            else:
                commit_lines.append(line)

    def open_blob(self, blob):
        return _OpenedGitBlob(
            self._object(blob._id).data_stream)

    def blob_size(self, blob):
        return self._object(blob._id).data_stream.size

    def _setup_hooks(self, source_path=None):
        'Set up the git post-commit hook'
        text = self.post_receive_template.substitute(
            url=self._repo.refresh_url())
        fn = os.path.join(self._repo.fs_path, self._repo.name,
                          'hooks', 'post-receive')
        with open(fn, 'w') as fp:
            fp.write(text)
        os.chmod(fn, 0o755)

    def _object(self, oid):
        evens = oid[::2]
        odds = oid[1::2]
        binsha = b''
        for e, o in zip(evens, odds):
            binsha += bytes((int(e + o, 16),))
        return git.Object.new_from_sha(self._git, binsha)

    def rev_parse(self, rev):
        return self._git.rev_parse(rev)

    def symbolics_for_commit(self, commit):
        try:
            branches = [
                b.name for b in self.branches if b.object_id == commit._id]
            tags = [t.name for t in self.tags if t.object_id == commit._id]
            return branches, tags
        except git.GitCommandError:
            return [], []

    def compute_tree_new(self, commit, tree_path='/'):
        ci = self._git.rev_parse(commit._id)
        tree = self.refresh_tree_info(ci.tree, set())
        return tree._id

    def tarball(self, commit, path=None):
        """
        :param path: is currently ignored.  Can't request a snapshot of a subdirectory
        """
        if not os.path.exists(self._repo.tarball_path):
            os.makedirs(self._repo.tarball_path)
        archive_name = self._repo.tarball_filename(commit)
        filename = os.path.join(self._repo.tarball_path, '%s%s' %
                                (archive_name, '.zip'))
        tmpfilename = os.path.join(self._repo.tarball_path, '%s%s' %
                                   (archive_name, '.tmp'))
        try:
            with open(tmpfilename, 'wb') as archive_file:
                self._git.archive(archive_file,
                                  format='zip', treeish=commit, prefix=archive_name + '/')
            os.rename(tmpfilename, filename)
        finally:
            if os.path.exists(tmpfilename):
                os.remove(tmpfilename)

    def is_empty(self):
        return not self.head

    def is_file(self, path, rev=None):
        path = path.strip('/')
        ci = self._git.rev_parse(rev)
        try:
            node = ci.tree / path
            return node.type == 'blob'
        except KeyError:
            return False

    def _get_refs(self, field_name):
        """ Returns a list of valid reference objects (branches or tags) from the git database

        :return: List of git ref objects.
        :rtype: list
        """

        cache_name = 'cached_' + field_name
        cache = getattr(self._repo, cache_name, None)

        if cache:
            return cache._deinstrument()  # always return a plain list

        refs = []
        start_time = time()
        ref_list = getattr(self._git, field_name)
        for ref in ref_list:
            try:
                hex_sha = ref.commit.hexsha
            except (ValueError, AssertionError) as e:
                log.debug(f"Found invalid sha: {ref}", exc_info=e)
                continue
            refs.append(Object(name=ref.name, object_id=hex_sha))
        time_taken = time() - start_time

        threshold = tg.config.get('repo_refs_cache_threshold')
        try:
            threshold = float(threshold) if threshold else None
        except ValueError:
            threshold = None
            log.warn('Skipping reference caching - The value for config param '
                     '"repo_refs_cache_threshold" must be a float.')

        if threshold is not None and time_taken > threshold:
            setattr(self._repo, cache_name, refs)
            sess = session(self._repo)
            if sess:
                sess.flush(self._repo)

        return refs

    @LazyProperty
    def head(self):
        if not self._git:
            return None
        # if the repo's HEAD file doesn't point to a valid branch, we need to select one
        # this can happen in particular with masterless repos
        if not self._git.head.is_valid():
            for head in self._git.heads:
                if head.is_valid():
                    self._git.head.reference = head
                    break
            else:
                return None  # no valid heads
        return self._git.head.commit.hexsha

    @LazyProperty
    def heads(self):
        return self._get_refs('heads')

    @LazyProperty
    def branches(self):
        return self._get_refs('branches')

    @LazyProperty
    def tags(self):
        return self._get_refs('tags')

    def set_default_branch(self, name):
        if not name:
            return
        self._repo.default_branch_name = name
        session(self._repo).flush(self._repo)

    def _get_last_commit(self, commit_id, paths):
        # git apparently considers merge commits to have "touched" a path
        # if the path is changed in either branch being merged, even though
        # the --name-only output doesn't include those files.  So, we have
        # to filter out the merge commits that don't actually include any
        # of the referenced paths in the list of files.
        files = []
        # don't skip first commit we're called with because it might be
        # a valid change commit; however...
        skip = 0
        while commit_id and not files:
            output = self._git.git.log(
                commit_id, '--', *[p for p in paths],
                pretty='format:%H',
                name_only=True,
                max_count=1,
                skip=skip)
            lines = output.split('\n')
            commit_id = lines[0]
            files = prefix_paths_union(paths, set(lines[1:]))
            # *do* skip subsequent merge commits or we'll get stuck on an infinite
            # loop matching and then diregarding the merge commit over and over
            skip = 1
        if commit_id:
            return commit_id, files
        else:
            return None, set()

    def get_changes(self, commit_id):
        return self._git.git.log(
            commit_id,
            name_only=True,
            pretty='format:%H',
            max_count=1).splitlines()[1:]

    def paged_diffs(self, commit_id, start=0, end=None, onlyChangedFiles=False):
        result = {'added': [], 'removed': [], 'changed': [], 'copied': [], 'renamed': []}
        cmd_args = ['--no-commit-id',
                    '--name-status',
                    '--no-abbrev',
                    '--root',
                    # show tree entry itself as well as subtrees (Commit.added_paths relies on this)
                    '-t',
                    '-z'  # don't escape filenames and use \x00 as fields delimiter
                    ]
        if onlyChangedFiles:
            cmd_args[4] = '-r'
        if asbool(tg.config.get('scm.commit.git.detect_copies', True)):
            cmd_args += ['-M', '-C']

        cmd_output = self._git.git.diff_tree(commit_id, *cmd_args).split('\x00')[:-1]  # don't escape filenames and use \x00 as fields delimiter

        ''' cmd_output will be like:
        [
        'A',
        'filename',
        'D',
        'another filename',
        'M',
        'po',
        'R100',  # <-- These next three lines would only show up with 'detect_copies' enabled
        'po/sr.po',
        'po/sr_Latn.po',
        ]
        '''

        x = 0
        files = []
        while x < len(cmd_output):
            status = cmd_output[x][0]
            if status in ('R', 'C'):
                ratio = float(cmd_output[x][1:4]) / 100.0
                files.append((status, {
                    'new': h.really_unicode(cmd_output[x + 2]),
                    'old': h.really_unicode(cmd_output[x + 1]),
                    'ratio': ratio,
                }))
                x += 3
            else:
                files.append((status, h.really_unicode(cmd_output[x + 1])))
                x += 2

        for status, name in files[start:end]:
            change_list_types = {
                'R': result['renamed'],
                'C': result['copied'],
                'A': result['added'],
                'D': result['removed'],
                'M': result['changed'],
                'T': result['changed'],
            }
            if status in change_list_types:
                change_list = change_list_types[status]
                change_list.append(name)
            else:
                log.error('Unexpected git change status: "%s" on file %s commit %s repo %s',
                          status, name, commit_id, self._repo.full_fs_path)

        result['total'] = len(files)

        return result

    @contextmanager
    def _shared_clone(self, from_path):
        tmp_path = tempfile.mkdtemp()
        start_time = time()
        self._git.git.clone('--bare', '--shared', from_path, tmp_path)
        tmp_repo = GitImplementation(Object(full_fs_path=tmp_path))
        log.info('Merge request view - shared clone timing: %s for %s', time()-start_time, from_path)
        try:
            yield tmp_repo
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)

    def merge_base(self, mr):
        g = self._git.git
        g.fetch(mr.app.repo.full_fs_path, mr.target_branch)
        return g.merge_base(mr.downstream.commit_id, 'FETCH_HEAD')

    def merge_request_commits(self, mr):
        """
        Return list of commits to be merged

        Must be called within mr.push_downstream_context()
        """
        use_tmp_dir = tg.config.get('scm.merge_list.git.use_tmp_dir', False)
        use_tmp_dir = asbool(use_tmp_dir)

        if use_tmp_dir:
            ctx_mgr = self._shared_clone(self._repo.full_fs_path)
        else:
            ctx_mgr = h.null_contextmanager(returning=self)

        with ctx_mgr as repo:
            base = repo.merge_base(mr)
            return list(repo.log(
                [mr.downstream.commit_id],
                exclude=[base],
                id_only=False))


class _OpenedGitBlob:
    CHUNK_SIZE = 4096

    def __init__(self, stream):
        self._stream = stream

    def read(self):
        return self._stream.read()

    def __iter__(self):
        '''
        Yields one line at a time, reading from the stream
        '''
        buffer = b''
        while True:
            # Replenish buffer until we have a line break
            while b'\n' not in buffer:
                chars = self._stream.read(self.CHUNK_SIZE)
                if not chars:
                    break
                buffer += chars
            if not buffer:
                break
            eol = buffer.find(b'\n')
            if eol == -1:
                # end without \n
                yield buffer
                break
            yield buffer[:eol + 1]
            buffer = buffer[eol + 1:]

    def close(self):
        pass

Mapper.compile_all()
