import logging
from itertools import chain
from cPickle import dumps

import bson

from ming.base import Object

from allura.lib import utils
from allura.model.repo import CommitDoc, TreeDoc, TreesDoc, DiffInfoDoc
from allura.model.repo import LastCommitDoc, CommitRunDoc
from allura.model.repo import Commit
from allura.model.index import ArtifactReferenceDoc, ShortlinkDoc

log = logging.getLogger(__name__)

QSIZE=100

def refresh_repo(repo, all_commits=False, notify=True):
    all_commit_ids = commit_ids = list(repo.all_commit_ids())
    if not all_commits:
        # Skip commits that are already in the DB
        commit_ids = unknown_commit_ids(commit_ids)
    log.info('Refreshing %d commits', len(commit_ids))

    # Refresh commits
    seen = set()
    for i, oid in enumerate(commit_ids):
        repo.refresh_commit_info(oid, seen)
        if (i+1) % 100 == 0:
            log.info('Refresh commit info %d: %s', (i+1), oid)

    refresh_commit_repos(all_commit_ids, repo)

    # Refresh child references
    for i, oid in enumerate(commit_ids):
        ci = CommitDoc.m.find(dict(_id=oid), validate=False).next()
        refresh_children(ci)
        if (i+1) % 100 == 0:
            log.info('Refresh child info %d for parents of %s', (i+1), ci._id)

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
        compute_diffs(repo._id, cache, ci)
        if (i+1) % 100 == 0:
            log.info('Compute diffs %d: %s', (i+1), ci._id)

    # Send notifications
    if notify:
        send_notifications(repo, commit_ids)

def refresh_commit_trees(ci, cache):
    '''Refresh the list of trees included withn a commit'''
    if ci.tree_id is None: return
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
                    url=repo.url() + 'ci/' + oid + '/'))
            # Always create a link for the full commit ID
            link1 = ShortlinkDoc(dict(
                    _id=bson.ObjectId(),
                    ref_id=index_id,
                    project_id=repo.app.config.project_id,
                    app_config_id=repo.app.config._id,
                    link=oid,
                    url=repo.url() + 'ci/' + oid + '/'))
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
                        commit_times=[ci.authored.date]))
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
    if rhs_ci.tree_id is None: return
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

def send_notifications(repo, commit_ids):
    '''Create appropriate notification and feed objects for a refresh'''
    from allura.model import Feed, Notification
    from allura.model.repository import config
    commit_msgs = []
    for oids in utils.chunked_iter(commit_ids, QSIZE):
        chunk = list(oids)
        index = dict(
            (doc._id, doc)
            for doc in Commit.query.find(dict(_id={'$in':chunk})))
        for oid in chunk:
            ci = index[oid]
            href = '%s%sci/%s/' % (
                config.common_prefix,
                repo.url(),
                oid)
            summary = _summarize(ci.message)
            item = Feed.post(
                repo, title='New commit',
                description='%s<br><a href="%s/">View Changes</a>' % (
                    summary, href))
            item.author_link = ci.author_url
            item.author_name = ci.authored.name
            commit_msgs.append('%s by %s <%s>' % (
                    summary, ci.authored.name, href))
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
            text = ci.message
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
