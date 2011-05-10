import sys
import logging
from collections import defaultdict
from itertools import chain, izip
from datetime import datetime

from pylons import c

from ming.base import Object

from allura import model as M
from allura.lib import helpers as h
from allura.lib import utils

log = logging.getLogger(__name__)

QSIZE=100

def dolog():
    h.set_context('test', 'code')
    repo = c.app.repo._impl._git
    oid = repo.commit(repo.heads[0]).hexsha
    log.info('start')
    for i, ci in enumerate(commitlog(oid)):
        print repr(ci)
    log.info('done')

def main():
    if len(sys.argv) > 1:
        h.set_context('test')
        c.project.install_app('Git', 'code', 'Code', init_from_url='/home/rick446/src/forge')
    h.set_context('test', 'code')
    M.repo.Commit.m.remove({})
    M.repo.Tree.m.remove({})
    M.repo.Trees.m.remove({})
    M.repo.DiffInfo.m.remove({})
    M.repo.BasicBlock.m.remove({})
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
    # commit_ids = commit_ids[:500]
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
        if ci is None: continue
        refresh_children(ci)
        if (i + j + 1) % 100 == 0:
            log.info('Refresh child (b) info %d: %s', (i + j + 1), ci._id)

    # Refresh basic blocks
    bbb = BasicBlockBuilder(commit_ids)
    bbb.run()

    # Verify the log
    log.info('Logging via basic blocks')
    with open('log.txt', 'w') as fp:
        for i, ci in enumerate(commitlog(commit_ids[0])):
            print >> fp, repr(ci)
            log.info('%r', ci)
    log.info('... done (%d commits from %s)', i, commit_ids[0])

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
    '''
    TODO: make sure we remove basic blocks created by previous refreshes when
    there are extra children added.
    '''
    M.repo.Commit.m.update_partial(
        dict(_id={'$in': ci.parent_ids}),
        {'$addToSet': dict(child_ids=ci._id)})

class BasicBlockBuilder(object):

    def __init__(self, commit_ids):
        self.commit_ids = commit_ids
        self.block_index = {} # by commit ID
        self.blocks = {}          # by block ID
        self.reasons = {}        # reasons to stop merging blocks

    def run(self):
        for oids in utils.chunked_iter(self.commit_ids, QSIZE):
            oids = list(oids)
            commits = list(M.repo.Commit.m.find(dict(_id={'$in':oids})))
            for ci in commits:
                if ci._id in self.block_index: continue
                self.block_index[ci._id] = ci._id
                self.blocks[ci._id] = M.repo.BasicBlock(dict(
                        _id=ci._id,
                        parent_commit_ids=ci.parent_ids,
                        commit_ids=[ci._id],
                        commit_times=[ci.authored.date]))
            self.merge_blocks()
        log.info('%d basic blocks', len(self.blocks))
        for bid, bb in sorted(self.blocks.items()):
            log.info('%32s: %r', self.reasons.get(bid, 'none'), bb)
        for bb in self.blocks.itervalues():
            bb.score = len(bb.commit_ids)
            bb.m.save()
        return self.blocks

    def merge_blocks(self):
        while True:
            for bid, bb in self.blocks.iteritems():
                if len(bb.parent_commit_ids) != 1:
                    self.reasons[bid] = '%d parents' % len(bb.parent_commit_ids)
                    continue
                p_oid = bb.parent_commit_ids[0]
                p_bid = self.block_index.get(p_oid)
                if p_bid is None:
                    self.reasons[bid] = 'parent commit not found'
                    continue
                p_bb = self.blocks.get(p_bid)
                if p_bb is None:
                    self.reasons[bid] = 'parent block not found'
                    continue
                if p_bb.commit_ids[0] != p_oid:
                    self.reasons[bid] = 'parent does not start with parent commit'
                    continue
                bb.commit_ids += p_bb.commit_ids
                bb.commit_times += p_bb.commit_times
                bb.parent_commit_ids = p_bb.parent_commit_ids
                for oid in p_bb.commit_ids:
                    self.block_index[oid] = bid
                break
            else:
                break
            del self.blocks[p_bid]

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

def commitlog(commit_id, skip=0, limit=sys.maxint):

    seen = set()
    def _visit(commit_id):
        if commit_id in seen: return
        bb = M.repo.BasicBlock.m.find(
            dict(commit_ids=commit_id)).sort('score', -1).first()
        if bb is None: return
        index = False
        for pos, (oid, time) in enumerate(izip(bb.commit_ids, bb.commit_times)):
            if oid == commit_id: index = True
            elif not index: continue
            seen.add(oid)
            ci_times[oid] = time
            if pos+1 < len(bb.commit_ids):
                ci_parents[oid] = [ bb.commit_ids[pos+1] ]
            else:
                ci_parents[oid] = bb.parent_commit_ids
        for oid in bb.parent_commit_ids:
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

    # Load all the blocks to build a commit graph
    ci_times = {}
    ci_parents = {}
    ci_children = defaultdict(set)
    log.info('Build commit graph')
    _visit(commit_id)
    for oid, parents in ci_parents.iteritems():
        for ci_parent in parents:
            ci_children[ci_parent].add(oid)

    # Convert oids to commit objects
    log.info('Traverse commit graph')
    for oids in utils.chunked_iter(_gen_ids(commit_id, skip, limit), QSIZE):
        oids = list(oids)
        index = dict(
            (ci._id, ci) for ci in M.repo.Commit.m.find(dict(_id={'$in': oids})))
        for oid in oids:
            yield index[oid]

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
    # dolog()
