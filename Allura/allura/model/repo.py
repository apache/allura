import re
import sys
import logging
from hashlib import sha1
from itertools import izip, chain
from datetime import datetime
from collections import defaultdict

from pylons import g

from ming import Field, Index, collection
from ming import schema as S
from ming.base import Object
from ming.utils import LazyProperty
from ming.orm import mapper

from allura.lib import utils
from allura.lib import helpers as h

from .auth import User
from .session import main_doc_session, project_doc_session
from .session import repository_orm_session

log = logging.getLogger(__name__)

# Some schema types
SUser = dict(name=str, email=str, date=datetime)
SObjType=S.OneOf('blob', 'tree', 'submodule')

# Used for when we're going to batch queries using $in
QSIZE = 100
README_RE = re.compile('^README(\.[^.]*)?$', re.IGNORECASE)

# Basic commit information
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

# Basic tree information
TreeDoc = collection(
    'repo_tree', main_doc_session,
    Field('_id', str),
    Field('tree_ids', [dict(name=str, id=str)]),
    Field('blob_ids', [dict(name=str, id=str)]),
    Field('other_ids', [dict(name=str, id=str, type=SObjType)]))

# Information about the last commit to touch a tree/blob
LastCommitDoc = collection(
    'repo_last_commit', project_doc_session,
    Field('_id', str),
    Field('repo_id', S.ObjectId()),
    Field('object_id', str),
    Field('commit_info', dict(
        id=str,
        date=datetime,
        author=str,
        author_email=str,
        author_url=str,
        href=str,
        shortlink=str,
        summary=str)),
    Index('repo_id', 'object_id'))

# List of all trees contained within a commit
TreesDoc = collection(
    'repo_trees', main_doc_session,
    Field('_id', str),
    Field('tree_ids', [str]))

# Information about which things were added/removed in  commit
DiffInfoDoc = collection(
    'repo_diffinfo', main_doc_session,
    Field('_id', str),
    Field(
        'differences',
        [ dict(name=str, lhs_id=str, rhs_id=str)]))

# List of commit runs (a run is a linear series of single-parent commits)
CommitRunDoc = collection(
    'repo_commitrun', main_doc_session,
    Field('_id', str),
    Field('parent_commit_ids', [str]),
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

    @LazyProperty
    def legacy(self):
        return Object(object_id=self._id)

class Commit(RepoObject):
    # Ephemeral attrs
    repo=None

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
        if self.tree_id is None:
            self.tree_id = self.repo.compute_tree(self)
        if self.tree_id is None:
            return None
        t = Tree.query.get(_id=self.tree_id)
        if t is None:
            self.tree_id = self.repo.compute_tree(self)
            t = Tree.query.get(_id=self.tree_id)
        if t is not None: t.set_context(self)
        return t

    @LazyProperty
    def summary(self):
        message = h.really_unicode(self.message)
        first_line = message.split('\n')[0]
        return h.text.truncate(first_line, 50)

    def shorthand_id(self):
        return self.repo.shorthand_for_commit(self._id)

    @LazyProperty
    def symbolic_ids(self):
        return self.repo.symbolics_for_commit(self.legacy)

    def url(self):
        return self.repo.url_for_commit(self.legacy)

    def log_iter(self, skip, count):
        for oids in utils.chunked_iter(commitlog(self._id), QSIZE):
            oids = list(oids)
            commits = dict(
                (ci._id, ci) for ci in self.query.find(dict(
                        _id={'$in': oids})))
            for oid in oids:
                if skip:
                    skip -= 1
                    continue
                if count:
                    count -= 1
                    ci = commits[oid]
                    ci.set_context(self.repo)
                    yield ci
                else:
                    break

    def log(self, skip, count):
        return list(self.log_iter(skip, count))

    def count_revisions(self):
        result = 0
        for oid in commitlog(self._id): result += 1
        return result

    def context(self):
        result = dict(prev=None, next=None)
        if self.parent_ids:
            result['prev'] = self.query.get(_id=self.parent_ids[0])
        if self.child_ids:
            result['next'] = self.query.get(_id=self.child_ids[0])
        return result

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
        name = None
        text = ''
        for x in self.blob_ids:
            if README_RE.match(x.name):
                name = x.name
                text = self.repo.open_blob(Object(object_id=x.id)).read()
                text = h.really_unicode(text)
                break
        if text == '':
            text = '<p><em>Empty File</em></p>'
        else:
            renderer = g.pypeline_markup.renderer(name)
            if renderer[1]:
                text = g.pypeline_markup.render(name,text)
            else:
                text = '<pre>%s</pre>' % text
        return (name, text)

    def ls(self):
        # Load last commit info
        oids = [ x.id for x in chain(self.tree_ids, self.blob_ids, self.other_ids) ]
        lc_index = dict(
            (lc.object_id, lc.commit_info)
            for lc in LastCommitDoc.m.find(dict(
                    repo_id=self.repo._id,
                    object_id={'$in': oids})))
        results = []
        def _get_last_commit(oid):
            lc = lc_index.get(oid)
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
            return lc
        for x in sorted(self.tree_ids, key=lambda x:x.name):
            results.append(dict(
                    kind='DIR',
                    name=x.name,
                    href=x.name + '/',
                    last_commit=_get_last_commit(x.id)))
        for x in sorted(self.blob_ids, key=lambda x:x.name):
            results.append(dict(
                    kind='FILE',
                    name=x.name,
                    href=x.name + '/',
                    last_commit=_get_last_commit(x.id)))
        for x in sorted(self.other_ids, key=lambda x:x.name):
            results.append(dict(
                    kind=x.type,
                    name=x.name,
                    href=None,
                    last_commit=_get_last_commit(x.id)))
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
        d = dict((x.name, x) for x in self.other_ids)
        d.update(
            (x.name, dict(x, type='tree'))
            for x in self.tree_ids)
        d.update(
            (x.name, dict(x, type='blob'))
            for x in self.blob_ids)
        return d

    def is_blob(self, name):
        return self.by_name[name]['type'] == 'blob'

mapper(Commit, CommitDoc, repository_orm_session)
mapper(Tree, TreeDoc, repository_orm_session)

def commitlog(commit_id, skip=0, limit=sys.maxint):

    seen = set()
    def _visit(commit_id):
        if commit_id in seen: return
        run = CommitRunDoc.m.get(commit_ids=commit_id)
        if run is None: return
        index = False
        for pos, (oid, time) in enumerate(izip(run.commit_ids, run.commit_times)):
            if oid == commit_id: index = True
            elif not index: continue
            seen.add(oid)
            ci_times[oid] = time
            if pos+1 < len(run.commit_ids):
                ci_parents[oid] = [ run.commit_ids[pos+1] ]
            else:
                ci_parents[oid] = run.parent_commit_ids
        for oid in run.parent_commit_ids:
            _visit(oid)

    def _gen_ids(commit_id, skip, limit):
        # Traverse the graph in topo order, yielding commit IDs
        commits = set([commit_id])
        new_parent = None
        while commits and limit:
            # next commit is latest commit that's valid to log
            if new_parent in commits:
                ci = new_parent
            else:
                ci = max(commits, key=lambda ci:ci_times[ci])
            commits.remove(ci)
            if skip:
                skip -= 1
                continue
            else:
                limit -= 1
            yield ci
            # remove this commit from its parents children and add any childless
            # parents to the 'ready set'
            new_parent = None
            for oid in ci_parents[ci]:
                children = ci_children[oid]
                children.discard(ci)
                if not children:
                    commits.add(oid)
                    new_parent = oid

    # Load all the runs to build a commit graph
    ci_times = {}
    ci_parents = {}
    ci_children = defaultdict(set)
    log.info('Build commit graph')
    _visit(commit_id)
    for oid, parents in ci_parents.iteritems():
        for ci_parent in parents:
            ci_children[ci_parent].add(oid)

    return _gen_ids(commit_id, skip, limit)
