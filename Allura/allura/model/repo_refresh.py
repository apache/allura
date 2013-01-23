import logging
from itertools import chain
from cPickle import dumps
import re
import os

import bson

import tg

from pylons import g,c

from ming.base import Object
from ming.orm import mapper, session, ThreadLocalORMSession

from allura.lib import utils
from allura.lib import helpers as h
from allura.model.repo import CommitDoc, TreeDoc, TreesDoc, DiffInfoDoc
from allura.model.repo import LastCommitDoc, CommitRunDoc
from allura.model.repo import Commit, Tree, LastCommit, ModelCache
from allura.model.index import ArtifactReferenceDoc, ShortlinkDoc

log = logging.getLogger(__name__)

QSIZE=100

def refresh_repo(repo, all_commits=False, notify=True):
    all_commit_ids = commit_ids = list(repo.all_commit_ids())
    if not commit_ids:
        # the repo is empty, no need to continue
        return
    new_commit_ids = unknown_commit_ids(commit_ids)
    stats_log = h.log_action(log, 'commit')
    for ci in new_commit_ids:
        stats_log.info(
            '',
            meta=dict(
                module='scm-%s' % repo.repo_id,
                read='0'))
    if not all_commits:
        # Skip commits that are already in the DB
        commit_ids = new_commit_ids
    log.info('Refreshing %d commits on %s', len(commit_ids), repo.full_fs_path)

    # Refresh commits
    seen = set()
    for i, oid in enumerate(commit_ids):
        repo.refresh_commit_info(oid, seen, not all_commits)
        if (i+1) % 100 == 0:
            log.info('Refresh commit info %d: %s', (i+1), oid)

    refresh_commit_repos(all_commit_ids, repo)

    # Refresh child references
    for i, oid in enumerate(commit_ids):
        ci = CommitDoc.m.find(dict(_id=oid), validate=False).next()
        refresh_children(ci)
        if (i+1) % 100 == 0:
            log.info('Refresh child info %d for parents of %s', (i+1), ci._id)

    if repo._refresh_precompute:
        # Refresh commit runs
        commit_run_ids = commit_ids
        # Check if the CommitRuns for the repo are in a good state by checking for
        # a CommitRunDoc that contains the last known commit. If there isn't one,
        # the CommitRuns for this repo are in a bad state - rebuild them entirely.
        if commit_run_ids != all_commit_ids:
            last_commit = last_known_commit_id(all_commit_ids, new_commit_ids)
            log.info('Last known commit id: %s', last_commit)
            if not CommitRunDoc.m.find(dict(commit_ids=last_commit)).count():
                log.info('CommitRun incomplete, rebuilding with all commits')
                commit_run_ids = all_commit_ids
        log.info('Starting CommitRunBuilder for %s', repo.full_fs_path)
        rb = CommitRunBuilder(commit_run_ids)
        rb.run()
        rb.cleanup()
        log.info('Finished CommitRunBuilder for %s', repo.full_fs_path)

    # Refresh trees
    # Like diffs below, pre-computing trees for some SCMs is too expensive,
    # so we skip it here, then do it on-demand later.
    if repo._refresh_precompute:
        cache = {}
        for i, oid in enumerate(commit_ids):
            ci = CommitDoc.m.find(dict(_id=oid), validate=False).next()
            cache = refresh_commit_trees(ci, cache)
            if (i+1) % 100 == 0:
                log.info('Refresh commit trees %d: %s', (i+1), ci._id)

    # Compute diffs
    cache = {}
    # For some SCMs, we don't want to pre-compute the diffs because that
    # would be too expensive, so we skip them here and do them on-demand
    # with caching.
    if repo._refresh_precompute:
        for i, oid in enumerate(commit_ids):
            ci = CommitDoc.m.find(dict(_id=oid), validate=False).next()
            compute_diffs(repo._id, cache, ci)
            if (i+1) % 100 == 0:
                log.info('Compute diffs %d: %s', (i+1), ci._id)

    if repo._refresh_precompute:
        cache = ModelCache()
        for i, oid in enumerate(reversed(commit_ids)):
            ci = cache.get(Commit, dict(_id=oid))
            ci.set_context(repo)
            compute_lcds(ci, cache)
            ThreadLocalORMSession.flush_all()
            if (i+1) % 100 == 0:
                log.info('Compute last commit info %d: %s', (i+1), ci._id)


    log.info('Refresh complete for %s', repo.full_fs_path)
    g.post_event(
            'repo_refreshed',
            commit_number=len(commit_ids),
            new=bool(new_commit_ids))
    # Send notifications
    if notify:
        send_notifications(repo, commit_ids)

def refresh_commit_trees(ci, cache):
    '''Refresh the list of trees included withn a commit'''
    if ci.tree_id is None: return cache
    trees_doc = TreesDoc(dict(
            _id=ci._id,
            tree_ids = list(trees(ci.tree_id, cache))))
    trees_doc.m.save(safe=False)
    new_cache = dict(
        (oid, cache[oid])
        for oid in trees_doc.tree_ids)
    return new_cache

def refresh_commit_repos(all_commit_ids, repo):
    '''Refresh the list of repositories within which a set of commits are
    contained'''
    for oids in utils.chunked_iter(all_commit_ids, QSIZE):
        for ci in CommitDoc.m.find(dict(
                _id={'$in':list(oids)},
                repo_ids={'$ne': repo._id})):
            oid = ci._id
            ci.repo_ids.append(repo._id)
            index_id = 'allura.model.repo.Commit#' + oid
            ref = ArtifactReferenceDoc(dict(
                    _id=index_id,
                    artifact_reference=dict(
                        cls=bson.Binary(dumps(Commit)),
                        project_id=repo.app.config.project_id,
                    app_config_id=repo.app.config._id,
                        artifact_id=oid),
                    references=[]))
            link0 = ShortlinkDoc(dict(
                    _id=bson.ObjectId(),
                    ref_id=index_id,
                    project_id=repo.app.config.project_id,
                    app_config_id=repo.app.config._id,
                    link=repo.shorthand_for_commit(oid)[1:-1],
                    url=repo.url_for_commit(oid)))
            # Always create a link for the full commit ID
            link1 = ShortlinkDoc(dict(
                    _id=bson.ObjectId(),
                    ref_id=index_id,
                    project_id=repo.app.config.project_id,
                    app_config_id=repo.app.config._id,
                    link=oid,
                    url=repo.url_for_commit(oid)))
            ci.m.save(safe=False, validate=False)
            ref.m.save(safe=False, validate=False)
            link0.m.save(safe=False, validate=False)
            link1.m.save(safe=False, validate=False)

def refresh_children(ci):
    '''Refresh the list of children of the given commit'''
    CommitDoc.m.update_partial(
        dict(_id={'$in': ci.parent_ids}),
        {'$addToSet': dict(child_ids=ci._id)},
        multi=True)

class CommitRunBuilder(object):
    '''Class used to build up linear runs of single-parent commits'''

    def __init__(self, commit_ids):
        self.commit_ids = commit_ids
        self.run_index = {} # by commit ID
        self.runs = {}          # by run ID
        self.reasons = {}    # reasons to stop merging runs

    def run(self):
        '''Build up the runs'''
        for oids in utils.chunked_iter(self.commit_ids, QSIZE):
            oids = list(oids)
            for ci in CommitDoc.m.find(dict(_id={'$in':oids})):
                if ci._id in self.run_index: continue
                self.run_index[ci._id] = ci._id
                self.runs[ci._id] = CommitRunDoc(dict(
                        _id=ci._id,
                        parent_commit_ids=ci.parent_ids,
                        commit_ids=[ci._id],
                        commit_times=[ci.authored['date']]))
            self.merge_runs()
        log.info('%d runs', len(self.runs))
        for rid, run in sorted(self.runs.items()):
            log.info('%32s: %r', self.reasons.get(rid, 'none'), run._id)
        for run in self.runs.itervalues():
            run.m.save()
        return self.runs

    def _all_runs(self):
        '''Find all runs containing this builder's commit IDs'''
        runs = {}
        for oids in utils.chunked_iter(self.commit_ids, QSIZE):
            oids = list(oids)
            for run in CommitRunDoc.m.find(dict(commit_ids={'$in': oids})):
                runs[run._id] = run
            for run in CommitRunDoc.m.find(dict(parent_commit_ids={'$in': oids})):
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
        '''Delete non-maximal runs and merge any new runs with existing runs'''
        runs = dict(
            (run['commit_ids'][0], run)
            for run in self._all_runs())
        for rid, run in runs.items():
            p_cis = run['parent_commit_ids']
            if len(p_cis) != 1: continue
            parent_run = runs.get(p_cis[0], None)
            if parent_run is None: continue
            run['commit_ids'] += parent_run['commit_ids']
            run['commit_times'] += parent_run['commit_times']
            run['parent_commit_ids'] = parent_run['parent_commit_ids']
            run.m.save()
            parent_run.m.delete()
            del runs[p_cis[0]]
        for run1 in runs.values():
            # if run1 is a subset of another run, delete it
            if CommitRunDoc.m.find(dict(commit_ids={'$all': run1.commit_ids},
                    _id={'$ne': run1._id})).count():
                log.info('... delete %r (subset of another run)', run1)
                run1.m.delete()
                continue
            for run2 in CommitRunDoc.m.find(dict(
                    commit_ids=run1.commit_ids[0])):
                if run1._id == run2._id: continue
                log.info('... delete %r (part of %r)', run2, run1)
                run2.m.delete()

    def merge_runs(self):
        '''Find partial runs that may be merged and merge them'''
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

def trees(id, cache):
    '''Recursively generate the list of trees contained within a given tree ID'''
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
    '''filter out all commit ids that have already been cached'''
    result = []
    for chunk in utils.chunked_iter(all_commit_ids, QSIZE):
        chunk = list(chunk)
        q = CommitDoc.m.find(dict(_id={'$in':chunk}))
        known_commit_ids = set(ci._id for ci in q)
        result += [ oid for oid in chunk if oid not in known_commit_ids ]
    return result

def compute_diffs(repo_id, tree_cache, rhs_ci):
    '''compute simple differences between a commit and its first parent'''
    if rhs_ci.tree_id is None: return tree_cache

    def _update_cache(lhs_tree_ids, rhs_tree_ids):
        # crazy cache logic that I'm not certain I understand
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
        return tree_index

    empty_tree = Object(_id=None, tree_ids=[], blob_ids=[], other_ids=[])
    commit_info = get_commit_info(rhs_ci)
    differences = []
    rhs_treesdoc = TreesDoc.m.get(_id=rhs_ci._id)
    if not rhs_treesdoc:
        # FIXME: These sometimes don't exist for unknown reasons; they should be auto-gen'ed
        log.error('Missing TreesDoc: %s', rhs_ci)
        return tree_cache
    for lhs_cid in rhs_ci.parent_ids:
        lhs_ci = CommitDoc.m.get(_id=lhs_cid)
        if lhs_ci is None:
            log.error('Commit ID referenced as parent but not found: %s parent of %s', lhs_cid, rhs_ci)
            continue
        lhs_treesdoc = TreesDoc.m.get(_id=lhs_cid)
        if not lhs_treesdoc:
            # FIXME: These sometimes don't exist for unknown reasons; they should be auto-gen'ed
            log.error('Missing TreesDoc: %s', rhs_ci)
            continue
        tree_index = _update_cache(lhs_treesdoc.tree_ids, rhs_treesdoc.tree_ids)
        rhs_tree = tree_index[rhs_ci.tree_id]
        lhs_tree = tree_index.get(lhs_ci.tree_id, empty_tree)
        for name, lhs_id, rhs_id in _diff_trees(lhs_tree, rhs_tree, tree_index):
            differences.append(
                dict(name=name, lhs_id=lhs_id, rhs_id=rhs_id))
    if not rhs_ci.parent_ids:
        # no parents, so everything in rhs is new
        tree_index = _update_cache([], rhs_treesdoc.tree_ids)
        rhs_tree = tree_index[rhs_ci.tree_id]
        for name, lhs_id, rhs_id in _diff_trees(empty_tree, rhs_tree, tree_index):
            differences.append(
                dict(name=name, lhs_id=lhs_id, rhs_id=rhs_id))
    # Build the diffinfo
    di = DiffInfoDoc(dict(
            _id=rhs_ci._id,
            differences=differences))
    di.m.save()
    return tree_cache

def send_notifications(repo, commit_ids):
    '''Create appropriate notification and feed objects for a refresh'''
    from allura.model import Feed, Notification
    commit_msgs = []
    base_url = tg.config.get('base_url', 'sourceforge.net')
    for oids in utils.chunked_iter(commit_ids, QSIZE):
        chunk = list(oids)
        index = dict(
            (doc._id, doc)
            for doc in Commit.query.find(dict(_id={'$in':chunk})))
        for oid in chunk:
            ci = index[oid]
            href = repo.url_for_commit(oid)
            summary = _summarize(ci.message)
            Feed.post(
                repo, title='New commit',
                description='%s<br><a href="%s">View Changes</a>' % (
                    summary, href),
                author_link=ci.author_url,
                author_name=ci.authored.name)
            branches = repo.symbolics_for_commit(ci)[0]
            commit_msgs.append('%s: %s by %s %s%s' % (
                    ",".join(b for b in branches),
                    summary, ci.authored.name, base_url, ci.url()))
    if commit_msgs:
        if len(commit_msgs) > 1:
            subject = '%d new commits to %s %s' % (
                len(commit_msgs), repo.app.project.name, repo.app.config.options.mount_label)
            text='\n\n'.join(commit_msgs)
        else:
            subject = '%s committed to %s %s: %s' % (
                ci.authored.name,
                repo.app.project.name,
                repo.app.config.options.mount_label,
                summary)
            branches = repo.symbolics_for_commit(ci)[0]
            text = "%s: %s %s%s" % (",".join(b for b in branches),
                               ci.message,
                               base_url, ci.url())

        Notification.post(
            artifact=repo,
            topic='metadata',
            subject=subject,
            text=text)

def _summarize(message):
    if not message: return ''
    summary = []
    for line in message.splitlines():
        line = line.rstrip()
        if line: summary.append(line)
        else: break
    return ' '.join(summary)

def _diff_trees(lhs, rhs, index, *path):
    def _fq(name):
        return '/'.join(reversed(
                (name,) + path))
    # Diff the trees
    rhs_tree_ids = dict(
        (o.name, o.id)
        for o in rhs.tree_ids)
    for o in lhs.tree_ids:
        rhs_id = rhs_tree_ids.pop(o.name, None)  # remove so won't be picked up as added, below
        if rhs_id == o.id:  # no change
            continue
        elif rhs_id is None:  # removed
            yield (_fq(o.name), o.id, None)
            rhs_tree = Object(_id=None, tree_ids=[], blob_ids=[], other_ids=[])
        else:  # changed
            rhs_tree = index[rhs_id]
        for difference in _diff_trees(index[o.id], rhs_tree, index, o.name, *path):
            yield difference
    for name, id in rhs_tree_ids.items():  # added
        yield (_fq(name), None, id)
        lhs_tree = Object(_id=None, tree_ids=[], blob_ids=[], other_ids=[])
        for difference in _diff_trees(lhs_tree, index[id], index, name, *path):
            yield difference
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

def get_commit_info(commit):
    if not isinstance(commit, Commit):
        commit = mapper(Commit).create(commit, dict(instrument=False))
    sess = session(commit)
    if sess: sess.expunge(commit)
    return dict(
        id=commit._id,
        author=commit.authored.name,
        author_email=commit.authored.email,
        date=commit.authored.date,
        author_url=commit.author_url,
        shortlink=commit.shorthand_id(),
        summary=commit.summary
        )

def last_known_commit_id(all_commit_ids, new_commit_ids):
    """
    Return the newest "known" (cached in mongo) commit id.

    Params:
        all_commit_ids: Every commit id from the repo on disk, sorted oldest to
                        newest.
        new_commit_ids: Commit ids that are not yet cached in mongo, sorted
                        oldest to newest.
    """
    if not all_commit_ids: return None
    if not new_commit_ids: return all_commit_ids[-1]
    return all_commit_ids[all_commit_ids.index(new_commit_ids[0]) - 1]


def compute_lcds(commit, cache):
    '''
    Compute LastCommit data for every Tree node under this tree.
    '''
    trees = cache.get(TreesDoc, dict(_id=commit._id))
    if not trees:
        log.error('Missing TreesDoc for %s; skipping compute_lcd' % commit)
        return
    with h.push_config(c, model_cache=cache):
        _update_tree_cache(trees.tree_ids, cache)
        tree = _pull_tree(cache, commit.tree_id, commit)
        _compute_lcds(tree, cache)

def _compute_lcds(tree, cache):
    cache._processed_trees += 1
    if tree.path().strip('/') not in tree.commit.changed_paths:
        cache._skipped_trees += 1
        return
    lcd = LastCommit.get(tree, create=True)  # auto-vivify LCD
    for x in tree.tree_ids:
        sub_tree = _pull_tree(cache, x.id, tree, x.name)
        _compute_lcds(sub_tree, cache)

def _pull_tree(cache, tree_id, *context):
    '''
    Since the Tree instances stick around in our cache,
    subsequent calls to set_context are overwriting our
    in-use copies and confusing the walk.  So, make an
    memory-only copy for our use.
    '''
    cache_tree = cache.get(Tree, dict(_id=tree_id))
    new_tree = Tree(
            _id=cache_tree._id,
            tree_ids=cache_tree.tree_ids,
            blob_ids=cache_tree.blob_ids,
            other_ids=cache_tree.other_ids,
        )
    session(new_tree).expunge(new_tree)
    new_tree.set_context(*context)
    return new_tree

def _update_tree_cache(tree_ids, cache):
    current_ids = set(tree_ids)
    cached_ids = set(cache.instance_ids(Tree))
    new_ids = current_ids - cached_ids
    cache.batch_load(Tree, {'_id': {'$in': list(new_ids)}})
