import sys
import logging
from itertools import chain
from datetime import datetime

from pylons import c

from ming.base import Object

from allura import model as M
from allura.lib import helpers as h
from allura.lib import utils

log = logging.getLogger(__name__)

def main():
    if len(sys.argv) > 1:
        h.set_context('test')
        c.project.install_app('Git', 'code', 'Code', init_from_url='/home/rick446/src/forge')
    h.set_context('test', 'code')
    M.repo.Commit.m.remove({})
    M.repo.Tree.m.remove({})
    M.repo.Trees.m.remove({})
    M.repo.DiffInfo.m.remove({})
    repo = c.app.repo._impl._git

    # Get all commits
    seen = set()
    all_commit_ids = []
    for head in repo.heads:
        for ci in repo.iter_commits(head, topo_order=True):
            if ci.binsha in seen: continue
            seen.add(ci.binsha)
            all_commit_ids.append(ci.hexsha)

    # Skip commits that are already in the DB
    commit_ids = unknown_commit_ids(all_commit_ids)
    log.info('Refreshing %d commits', len(commit_ids))

    # Refresh commits
    for i, oid in enumerate(commit_ids):
        ci = repo.rev_parse(oid)
        refresh_commit_info(ci, seen)
        if (i+1) % 100 == 0:
            log.info('Refresh commit info %d: %s', (i+1), oid)

    # Refresh child references
    seen = set()
    parents = set()
    for i, oid in enumerate(commit_ids):
        ci = M.repo.Commit.m.get(_id=oid)
        refresh_children(ci)
        seen.add(ci._id)
        parents.update(ci.parent_ids)
        if (i+1) % 100 == 0:
            log.info('Refresh child (a) info %d: %s', (i+1), ci._id)
    for j, oid in enumerate(parents-seen):
        ci = M.repo.Commit.m.get(_id=oid)
        parents.update(ci.parent_ids)
        if (i + j + 1) % 100 == 0:
            log.info('Refresh child (b) info %d: %s', (i + j + 1), ci._id)

    # Refresh basic blocks

    # Refresh trees
    cache = {}
    for i, oid in enumerate(commit_ids):
        ci = M.repo.Commit.m.get(_id=oid)
        cache = refresh_commit_trees(ci, cache)
        if (i+1) % 100 == 0:
            log.info('Refresh commit trees %d: %s', (i+1), ci._id)

    # Compute diffs
    cache = {}
    for i, oid in enumerate(commit_ids):
        ci = M.repo.Commit.m.get(_id=oid)
        compute_diffs(cache, ci)
        if (i+1) % 100 == 0:
            log.info('Compute diffs %d: %s', (i+1), ci._id)

def refresh_commit_trees(ci, cache):
    trees_doc = M.repo.Trees(dict(
            _id=ci._id,
            tree_ids = list(trees(ci.tree_id, cache))))
    trees_doc.m.save(safe=False)
    new_cache = dict(
        (oid, cache[oid])
        for oid in trees_doc.tree_ids)
    return new_cache

def refresh_commit_info(ci, seen):
    ci_doc = M.repo.Commit(dict(
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
    refresh_tree(ci.tree, seen)
    ci_doc.m.save(safe=False)
    return True

def refresh_children(ci):
    M.repo.Commit.m.update_partial(
        dict(_id={'$in': ci.parent_ids}),
        {'$addToSet': dict(child_ids=ci._id)})

def refresh_tree(t, seen):
    if t.binsha in seen: return
    seen.add(t.binsha)
    doc = M.repo.Tree(dict(
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
        t = M.repo.Tree.m.get(_id=id)
        entries = [ o.id for o in t.tree_ids ]
        cache[id] = entries
    for i in entries:
        for x in trees(i, cache):
            yield x

def unknown_commit_ids(all_commit_ids):
    QSIZE=100
    result = []
    for chunk in utils.chunked_iter(all_commit_ids, QSIZE):
        q = M.repo.Commit.m.find(_id={'$in':chunk})
        known_commit_ids = set(ci._id for ci in q)
        result += [ oid for oid in chunk if oid not in known_commit_ids ]
    return result

def compute_diffs(tree_cache, rhs_ci, lhs_ci=None):
    rhs_tree_ids = M.repo.Trees.m.get(_id=rhs_ci._id).tree_ids
    if lhs_ci is None and rhs_ci.parent_ids:
        lhs_ci = M.repo.Commit.m.get(_id=rhs_ci.parent_ids[0])
    if lhs_ci is not None:
        lhs_tree_ids = M.repo.Trees.m.get(_id=lhs_ci._id).tree_ids
    else:
        lhs_tree_ids = []
    new_tree_ids = [
        tid for tid in chain(lhs_tree_ids, rhs_tree_ids)
        if tid not in tree_cache ]
    tree_index = dict(
        (t._id, t) for t in M.repo.Tree.m.find(dict(_id={'$in': new_tree_ids}),validate=False))
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
    differences = [
        dict(name=name, lhs_id=lhs_id, rhs_id=rhs_id)
        for name, lhs_id, rhs_id in _diff_trees(lhs_tree, rhs_tree, tree_index) ]
    di = M.repo.DiffInfo(dict(
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

if __name__ == '__main__':
    main()
