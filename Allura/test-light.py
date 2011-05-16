import sys
import logging
from collections import defaultdict
from itertools import chain, izip
from datetime import datetime
from cPickle import dumps

import bson
from pylons import c
from pymongo.errors import DuplicateKeyError

from ming.base import Object

from allura.lib import helpers as h
from allura.lib import utils
from allura.model.repo import CommitDoc, TreeDoc, TreesDoc, DiffInfoDoc
from allura.model.repo import LastCommitDoc, CommitRunDoc
from allura.model.repo import Commit
from allura.model.index import ArtifactReferenceDoc, ShortlinkDoc

log = logging.getLogger(__name__)

QSIZE=100

def main():
    if len(sys.argv) > 1:
        h.set_context('test')
        c.project.install_app('Git', 'code', 'Code', init_from_url='/home/rick446/src/forge')
    h.set_context('test', 'code')
    CommitDoc.m.remove({})
    TreeDoc.m.remove({})
    TreesDoc.m.remove({})
    DiffInfoDoc.m.remove({})
    LastCommitDoc.m.remove({})
    CommitRunDoc.m.remove({})

    # Get all commits (repo-specific)
    all_commit_ids = list(c.app.repo.all_commit_ids())

    # Skip commits that are already in the DB (repo-agnostic)
    commit_ids = unknown_commit_ids(all_commit_ids)
    # commit_ids = commit_ids[:500]
    log.info('Refreshing %d commits', len(commit_ids))

    # Refresh commits (repo-specific)
    seen = set()
    for i, oid in enumerate(commit_ids):
        c.app.repo.refresh_commit_info(oid, seen)
        if (i+1) % 100 == 0:
            log.info('Refresh commit info %d: %s', (i+1), oid)

    #############################################
    # Everything below here is repo-agnostic
    #############################################

    refresh_repo(commit_ids, c.app.repo)

    # Refresh child references
    seen = set()
    parents = set()

    for i, oid in enumerate(commit_ids):
        ci = CommitDoc.m.find(dict(_id=oid), validate=False).next()
        refresh_children(ci)
        seen.add(ci._id)
        parents.update(ci.parent_ids)
        if (i+1) % 100 == 0:
            log.info('Refresh child (a) info %d: %s', (i+1), ci._id)
    for j, oid in enumerate(parents-seen):
        try:
            ci = CommitDoc.m.find(dict(_id=oid), validate=False).next()
        except StopIteration:
            continue
        refresh_children(ci)
        if (i + j + 1) % 100 == 0:
            log.info('Refresh child (b) info %d: %s', (i + j + 1), ci._id)

    # Refresh commit runs
    rb = CommitRunBuilder(commit_ids)
    rb.run()
    rb.cleanup()

    # Refresh trees
    cache = {}
    for i, oid in enumerate(commit_ids):
        ci = CommitDoc.m.find(dict(_id=oid), validate=False).next()
        cache = refresh_commit_trees(ci, cache)
        if (i+1) % 100 == 0:
            log.info('Refresh commit trees %d: %s', (i+1), ci._id)

    # Compute diffs
    cache = {}
    for i, oid in enumerate(commit_ids):
        ci = CommitDoc.m.find(dict(_id=oid), validate=False).next()
        compute_diffs(c.app.repo._id, cache, ci)
        if (i+1) % 100 == 0:
            log.info('Compute diffs %d: %s', (i+1), ci._id)

def refresh_commit_trees(ci, cache):
    trees_doc = TreesDoc(dict(
            _id=ci._id,
            tree_ids = list(trees(ci.tree_id, cache))))
    trees_doc.m.save(safe=False)
    new_cache = dict(
        (oid, cache[oid])
        for oid in trees_doc.tree_ids)
    return new_cache

def refresh_commit_info(ci, seen):
    if CommitDoc.m.find(dict(_id=ci.hexsha)).count() != 0:
        return False
    try:
        ci_doc = CommitDoc(dict(
                _id=ci.hexsha,
                tree_id=ci.tree.hexsha,
                committed = Object(
                    name=h.really_unicode(ci.committer.name),
                    email=h.really_unicode(ci.committer.email),
                    date=datetime.utcfromtimestamp(
                        ci.committed_date-ci.committer_tz_offset)),
                authored = Object(
                    name=h.really_unicode(ci.author.name),
                    email=h.really_unicode(ci.author.email),
                    date=datetime.utcfromtimestamp(
                        ci.authored_date-ci.author_tz_offset)),
                message=h.really_unicode(ci.message or ''),
                child_ids=[],
                parent_ids = [ p.hexsha for p in ci.parents ]))
        ci_doc.m.insert(safe=True)
    except DuplicateKeyError:
        return False
    refresh_tree(ci.tree, seen)
    return True

def refresh_repo(commit_ids, repo):
    for oids in utils.chunked_iter(commit_ids, QSIZE):
        oids = list(oids)
        # Create shortlinks and artifactrefs
        for oid in oids:
            index_id = 'allura.model.repo.Commit#' + oid
            ref = ArtifactReferenceDoc(dict(
                    _id=index_id,
                    artifact_reference=dict(
                        cls=dumps(Commit),
                        project_id=repo.app.config.project_id,
                    app_config_id=repo.app.config._id,
                        artifact_id=oid),
                    references=[]))
            link = ShortlinkDoc(dict(
                    _id=bson.ObjectId(),
                    ref_id=index_id,
                    project_id=repo.app.config.project_id,
                    app_config_id=repo.app.config._id,
                    link=repo.shorthand_for_commit(oid),
                    url=repo.url() + 'ci/' + oid + '/'))
            ref.m.save(safe=False, validate=False)
            link.m.save(safe=False, validate=False)
        CommitDoc.m.update_partial(
            dict(
                _id={'$in': oids},
                repo_ids={'$ne': repo._id}),
            {'$addToSet': dict(repo_ids=repo._id)},
            multi=True)

def refresh_children(ci):
    CommitDoc.m.update_partial(
        dict(_id={'$in': ci.parent_ids}),
        {'$addToSet': dict(child_ids=ci._id)},
        multi=True)

class CommitRunBuilder(object):

    def __init__(self, commit_ids):
        self.commit_ids = commit_ids
        self.run_index = {} # by commit ID
        self.runs = {}          # by run ID
        self.reasons = {}    # reasons to stop merging runs

    def run(self):
        for oids in utils.chunked_iter(self.commit_ids, QSIZE):
            oids = list(oids)
            commits = list(CommitDoc.m.find(dict(_id={'$in':oids})))
            for ci in commits:
                if ci._id in self.run_index: continue
                self.run_index[ci._id] = ci._id
                self.runs[ci._id] = CommitRunDoc(dict(
                        _id=ci._id,
                        parent_commit_ids=ci.parent_ids,
                        commit_ids=[ci._id],
                        commit_times=[ci.authored.date]))
            self.merge_runs()
        log.info('%d runs', len(self.runs))
        for rid, run in sorted(self.runs.items()):
            log.info('%32s: %r', self.reasons.get(rid, 'none'), run._id)
        for run in self.runs.itervalues():
            run.m.save()
        return self.runs

    def _all_runs(self):
        runs = {}
        for oids in utils.chunked_iter(self.commit_ids, QSIZE):
            oids = list(oids)
            for run in CommitRunDoc.m.find(dict(commit_ids={'$in': oids})):
                runs[run._id] = run
        seen_run_ids = set()
        runs = runs.values()
        while runs:
            run = runs.pop()
            if run._id in seen_run_ids: continue
            seen_run_ids.add(run._id)
            yield run
            for run in CommitRunDoc.m.find(
                dict(commit_ids={'$in':run.parent_commit_ids})):
                runs.append(run)

    def cleanup(self):
        '''Delete non-maximal runs'''
        for run1 in self._all_runs():
            for run2 in CommitRunDoc.m.find(dict(
                    commit_ids=run1.commit_ids[0])):
                if run1._id == run2._id: continue
                log.info('... delete %r (part of %r)', run2, run1)
                run2.m.delete()

    def merge_runs(self):
        while True:
            for run_id, run in self.runs.iteritems():
                if len(run.parent_commit_ids) != 1:
                    self.reasons[run_id] = '%d parents' % len(run.parent_commit_ids)
                    continue
                p_oid = run.parent_commit_ids[0]
                p_run_id = self.run_index.get(p_oid)
                if p_run_id is None:
                    self.reasons[run_id] = 'parent commit not found'
                    continue
                p_run = self.runs.get(p_run_id)
                if p_run is None:
                    self.reasons[run_id] = 'parent run not found'
                    continue
                if p_run.commit_ids[0] != p_oid:
                    self.reasons[run_id] = 'parent does not start with parent commit'
                    continue
                run.commit_ids += p_run.commit_ids
                run.commit_times += p_run.commit_times
                run.parent_commit_ids = p_run.parent_commit_ids
                for oid in p_run.commit_ids:
                    self.run_index[oid] = run_id
                break
            else:
                break
            del self.runs[p_run_id]

def refresh_tree(t, seen):
    if t.binsha in seen: return
    seen.add(t.binsha)
    doc = TreeDoc(dict(
            _id=t.hexsha,
            tree_ids=[],
            blob_ids=[],
            other_ids=[]))
    for o in t:
        obj = Object(
            name=h.really_unicode(o.name),
            id=o.hexsha)
        if o.type == 'tree':
            refresh_tree(o, seen)
            doc.tree_ids.append(obj)
        elif o.type == 'blob':
            doc.blob_ids.append(obj)
        else:
            obj.type = o.type
            doc.other_ids.append(obj)
    doc.m.save(safe=False)

def trees(id, cache):
    yield id
    entries = cache.get(id, None)
    if entries is None:
        t = TreeDoc.m.get(_id=id)
        entries = [ o.id for o in t.tree_ids ]
        cache[id] = entries
    for i in entries:
        for x in trees(i, cache):
            yield x

def unknown_commit_ids(all_commit_ids):
    result = []
    for chunk in utils.chunked_iter(all_commit_ids, QSIZE):
        q = CommitDoc.m.find(_id={'$in':chunk})
        known_commit_ids = set(ci._id for ci in q)
        result += [ oid for oid in chunk if oid not in known_commit_ids ]
    return result

def compute_diffs(repo_id, tree_cache, rhs_ci):
    def _walk_tree(tree, tree_index):
        for x in tree.blob_ids: yield x.id
        for x in tree.other_ids: yield x.id
        for x in tree.tree_ids:
            yield x.id
            for xx in _walk_tree(tree_index[x.id], tree_index):
                yield xx

    rhs_tree_ids = TreesDoc.m.get(_id=rhs_ci._id).tree_ids
    if rhs_ci.parent_ids:
        lhs_ci = CommitDoc.m.get(_id=rhs_ci.parent_ids[0])
    else:
        lhs_ci = None
    if lhs_ci is not None:
        lhs_tree_ids = TreesDoc.m.get(_id=lhs_ci._id).tree_ids
    else:
        lhs_tree_ids = []
    new_tree_ids = [
        tid for tid in chain(lhs_tree_ids, rhs_tree_ids)
        if tid not in tree_cache ]
    tree_index = dict(
        (t._id, t) for t in TreeDoc.m.find(dict(_id={'$in': new_tree_ids}),validate=False))
    tree_index.update(tree_cache)
    rhs_tree_ids_set = set(rhs_tree_ids)
    tree_cache.clear()
    tree_cache.update(
        (id, t) for id,t in tree_index.iteritems() if id in rhs_tree_ids_set)
    rhs_tree = tree_index[rhs_ci.tree_id]
    if lhs_ci is None:
        lhs_tree = Object(_id=None, tree_ids=[], blob_ids=[], other_ids=[])
    else:
        lhs_tree = tree_index[lhs_ci.tree_id]
    differences = []
    for name, lhs_id, rhs_id in _diff_trees(lhs_tree, rhs_tree, tree_index):
        differences.append(
            dict(name=name, lhs_id=lhs_id, rhs_id=rhs_id))
        # Set last commit info
        if rhs_id is not None:
            _set_last_commit(repo_id, rhs_id, rhs_ci)
        rhs_tree = tree_index.get(rhs_id, None)
        if rhs_tree is not None:
            for oid in _walk_tree(rhs_tree, tree_index):
                _set_last_commit(repo_id, oid, rhs_ci)
    di = DiffInfoDoc(dict(
            _id=rhs_ci._id,
            differences=differences))
    di.m.save()
    return tree_cache

def _diff_trees(lhs, rhs, index, *path):
    def _fq(name):
        return '/'.join(reversed(
                (name,) + path))
    # Diff the trees
    rhs_tree_ids = dict(
        (o.name, o.id)
        for o in rhs.tree_ids)
    for o in lhs.tree_ids:
        rhs_id = rhs_tree_ids.pop(o.name, None)
        if rhs_id == o.id:
            continue # no change
        elif rhs_id is None:
            yield (_fq(o.name), o.id, None)
        else:
            for difference in _diff_trees(
                index[o.id], index[rhs_id], index,
                o.name, *path):
                yield difference
    for name, id in rhs_tree_ids.items():
        yield (_fq(name), None, id)
    # DIff the blobs
    rhs_blob_ids = dict(
        (o.name, o.id)
        for o in rhs.blob_ids)
    for o in lhs.blob_ids:
        rhs_id = rhs_blob_ids.pop(o.name, None)
        if rhs_id == o.id:
            continue # no change
        elif rhs_id is None:
            yield (_fq(o.name), o.id, None)
        else:
            yield (_fq(o.name), o.id, rhs_id)
    for name, id in rhs_blob_ids.items():
        yield (_fq(name), None, id)

def _set_last_commit(repo_id, oid, commit):
    lc = LastCommitDoc(dict(
            _id='%s:%s' % (repo_id, oid),
            repo_id=repo_id,
            object_id=oid,
            commit_info=dict(
                id=commit._id,
                author=commit.authored.name,
                author_email=commit.authored.email,
                date=commit.authored.date,
                # author_url=commit.author_url,
                # href=commit.url(),
                # shortlink=commit.shorthand_id(),
                # summary=commit.summary
                )))
    lc.m.save(safe=False)
    return lc

if __name__ == '__main__':
    main()
    # dolog()
