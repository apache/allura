import os
import re
import shutil
import string
import logging
from binascii import b2a_hex
from hashlib import sha1
from datetime import datetime
from cStringIO import StringIO
from ConfigParser import ConfigParser

import tg
from pylons import c
os.environ['HGRCPATH'] = '' # disable loading .hgrc
from mercurial import ui, hg

from ming.base import Object
from ming.orm import MappedClass, session
from ming.utils import LazyProperty

from allura import model as M
from allura.model.repository import topological_sort, GitLikeTree

log = logging.getLogger(__name__)

class Repository(M.Repository):
    tool_name='Hg'
    repo_id='hg'
    type_s='Hg Repository'
    class __mongometa__:
        name='hg-repository'

    def __init__(self, **kw):
        super(Repository, self).__init__(**kw)
        self._impl = HgImplementation(self)

    def readonly_clone_command(self):
        ro_path = self.readonly_path(c.user.username)
        if ro_path:
            return 'hg clone %s %s' % (ro_path, c.project.shortname.replace('/','.'))
        else:
            return None

    def readwrite_clone_command(self):
        rw_path = self.readwrite_path(c.user.username)
        return 'hg clone %s %s' % (rw_path, c.project.shortname.replace('/','.'))

    def readwrite_https_command(self):
        rw_https_path = self.readwrite_https_path(c.user.username)
        return 'hg clone %s %s' % (rw_https_path, c.project.shortname.replace('/','.'))

    def merge_command(self, merge_request):
        '''Return the command to merge a given commit into a given target branch'''
        return 'hg checkout %s;\nhg pull -r %s hg://%s; hg merge %s' % (
            merge_request.target_branch,
            merge_request.downstream.commit_id,
            merge_request.downstream.repo_url,
            merge_request.downstream.commit_id)

    def count(self, branch='default'):
        return super(Repository, self).count(branch)

    def log(self, branch='default', offset=0, limit=10):
        return super(Repository, self).log(branch, offset, limit)

class HgImplementation(M.RepositoryImplementation):
    re_hg_user = re.compile('(.*) <(.*)>')

    def __init__(self, repo):
        self._repo = repo

    @LazyProperty
    def _hg(self):
        return hg.repository(ui.ui(), self._repo.full_fs_path)

    def init(self):
        fullname = self._setup_paths()
        log.info('hg init %s', fullname)
        if os.path.exists(fullname):
            shutil.rmtree(fullname)
        repo = hg.repository(
            ui.ui(), self._repo.full_fs_path, create=True)
        self.__dict__['_hg'] = repo
        self._setup_special_files()
        self._repo.status = 'ready'

    def clone_from(self, source_url):
        '''Initialize a repo as a clone of another'''
        fullname = self._setup_paths(create_repo_dir=False)
        if os.path.exists(fullname):
            shutil.rmtree(fullname)
        log.info('Initialize %r as a clone of %s',
                 self._repo, source_url)
        src, repo = hg.clone(
            ui.ui(),
            source_url,
            self._repo.full_fs_path)
        self.__dict__['_hg'] = repo
        self._setup_special_files()
        self._repo.status = 'analyzing'
        session(self._repo).flush()
        log.info('... %r cloned, analyzing', self._repo)
        self._repo.refresh()
        self._repo.status = 'ready'
        log.info('... %s ready', self._repo)
        session(self._repo).flush()

    def commit(self, rev):
        result = M.Commit.query.get(object_id=rev)
        if result is None:
            try:
                impl = self._hg[str(rev)]
                result = M.Commit.query.get(object_id=impl.hex())
            except Exception, e:
                log.exception(e)
        if result is None: return None
        result.set_context(self._repo)
        return result

    def new_commits(self, all_commits=False):
        graph = {}
        to_visit = [ self._hg[hd.object_id] for hd in self._repo.heads ]
        while to_visit:
            obj = to_visit.pop()
            if obj.hex() in graph: continue
            if not all_commits:
                # Look up the object
                if M.Commit.query.find(dict(object_id=obj.hex())).count():
                    graph[obj.hex()] = set() # mark as parentless
                    continue
            graph[obj.hex()] = set(
                p.hex() for p in obj.parents()
                if p.hex() != obj.hex())
            to_visit += obj.parents()
        return list(topological_sort(graph))

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
        self._repo.heads = [
            Object(name=None, object_id=self._hg[head].hex())
            for head in self._hg.heads() ]
        self._repo.branches = [
            Object(name=name, object_id=self._hg[tag].hex())
            for name, tag in self._hg.branchtags().iteritems() ]
        self._repo.repo_tags = [
            Object(name=name, object_id=self._hg[tag].hex())
            for name, tag in self._hg.tags().iteritems() ]
        session(self._repo).flush()

    def refresh_commit(self, ci, seen_object_ids):
        obj = self._hg[ci.object_id]
        # Save commit metadata
        mo = self.re_hg_user.match(obj.user())
        if mo:
            user_name, user_email = mo.groups()
        else:
            user_name = user_email = obj.user()
        ci.committed = Object(
            name=user_name,
            email=user_email,
            date=datetime.utcfromtimestamp(sum(obj.date())))
        ci.authored=Object(ci.committed)
        ci.message=obj.description() or ''
        ci.parent_ids=[
            p.hex() for p in obj.parents()
            if p.hex() != obj.hex() ]
        # Save commit tree (must build a fake git-like tree from the changectx)
        fake_tree = self._tree_from_changectx(obj)
        ci.tree_id = fake_tree.hex()
        tree, isnew = M.Tree.upsert(fake_tree.hex())
        if isnew:
            tree.set_context(ci)
            self._refresh_tree(tree, fake_tree)

    def log(self, object_id, skip, count):
        obj = self._hg[object_id]
        candidates = [ obj ]
        result = []
        seen = set()
        while count and candidates:
            candidates.sort(key=lambda c:sum(c.date()))
            obj = candidates.pop(-1)
            if obj.hex() in seen: continue
            seen.add(obj.hex())
            if skip == 0:
                result.append(obj.hex())
                count -= 1
            else:
                skip -= 1
            candidates += obj.parents()
        return result, [ p.hex() for p in candidates ]

    def open_blob(self, blob):
        fctx = self._hg[blob.commit.object_id][blob.path()[1:]]
        return StringIO(fctx.data())

    def _setup_hooks(self):
        'Set up the hg changegroup hook'
        cp = ConfigParser()
        fn = os.path.join(self._repo.fs_path, self._repo.name, '.hg', 'hgrc')
        cp.read(fn)
        if not cp.has_section('hooks'):
            cp.add_section('hooks')
        url = (tg.config.get('base_url', 'http://localhost:8080')
               + '/auth/refresh_repo' + self._repo.url())
        cp.set('hooks','changegroup','curl -s %s' % url)
        with open(fn, 'w') as fp:
            cp.write(fp)
        os.chmod(fn, 0755)

    def _tree_from_changectx(self, changectx):
        '''Build a fake git-like tree from a changectx and its manifest'''
        root = GitLikeTree()
        for filepath in changectx.manifest():
            fctx = changectx[filepath]
            oid = b2a_hex(fctx.filenode())
            root.set_blob(filepath, oid)
        return root

    def _refresh_tree(self, tree, obj):
        tree.object_ids=[
            Object(object_id=o.hex(), name=name)
            for name, o in obj.trees.iteritems() ]
        tree.object_ids += [
            Object(object_id=oid, name=name)
            for name, oid in obj.blobs.iteritems() ]
        for name, o in obj.trees.iteritems():
            subtree, isnew = M.Tree.upsert(o.hex())
            if isnew:
                subtree.set_context(tree, name)
                self._refresh_tree(subtree, o)
        for name, oid in obj.blobs.iteritems():
            blob, isnew = M.Blob.upsert(oid)

    def symbolics_for_commit(self, commit):
        branch_heads, tags = super(self.__class__, self).symbolics_for_commit(commit)
        ctx = self._hg[commit.object_id]
        return [ctx.branch()], tags

MappedClass.compile_all()
