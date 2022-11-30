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

import logging
from six.moves.cPickle import dumps

import bson
import tg
import jinja2
from paste.deploy.converters import asint
from tg import tmpl_context as c, app_globals as g

from ming.orm import mapper, session, ThreadLocalORMSession
from ming.odm.base import ObjectState, state

from allura.lib import utils
from allura.lib.search import find_shortlinks
from allura.model.repository import Commit, CommitDoc
from allura.model.index import ArtifactReference, Shortlink
from allura.model.auth import User
from allura.model.timeline import TransientActor

log = logging.getLogger(__name__)

QSIZE = 100


def refresh_repo(repo, all_commits=False, notify=True, new_clone=False, commits_are_new=None):
    if commits_are_new is None:
        commits_are_new = not all_commits and not new_clone

    all_commit_ids = commit_ids = list(repo.all_commit_ids())[::-1]  # start with oldest
    if not commit_ids:
        # the repo is empty, no need to continue
        return
    new_commit_ids = unknown_commit_ids(commit_ids)
    if not all_commits:
        # Skip commits that are already in the DB
        commit_ids = new_commit_ids
    log.info('Refreshing %d commits on %s', len(commit_ids), repo.full_fs_path)

    # Refresh commits
    seen = set()
    for i, oid in enumerate(commit_ids):
        repo.refresh_commit_info(oid, seen, not all_commits)
        if (i + 1) % 100 == 0:
            log.info('Refresh commit info %d: %s', (i + 1), oid)

    refresh_commit_repos(all_commit_ids, repo)

    # Refresh child references
    for i, oid in enumerate(commit_ids):
        ci = next(CommitDoc.m.find(dict(_id=oid), validate=False))
        refresh_children(ci)
        if (i + 1) % 100 == 0:
            log.info('Refresh child info %d for parents of %s',
                     (i + 1), ci._id)

    # Clear any existing caches for branches/tags
    if repo.cached_branches:
        repo.cached_branches = []
        session(repo).flush()

    if repo.cached_tags:
        repo.cached_tags = []
        session(repo).flush()
    # The first view can be expensive to cache,
    # so we want to do it here instead of on the first view.
    repo.get_branches()
    repo.get_tags()

    if commits_are_new:
        for commit in commit_ids:
            new = repo.commit(commit)
            user = User.by_email_address(new.committed.email)
            if user is None:
                user = User.by_username(new.committed.name)
            if user is not None:
                g.statsUpdater.newCommit(new, repo.app_config.project, user)
            actor = user or TransientActor(
                    activity_name=new.committed.name or new.committed.email)
            g.director.create_activity(actor, 'committed', new, target=repo.app,
                                       related_nodes=[repo.app_config.project],
                                       tags=['commit', repo.tool.lower()])

        from allura.webhooks import RepoPushWebhookSender
        by_branches, by_tags = _group_commits(repo, commit_ids)
        params = []
        for b, commits in by_branches.items():
            ref = f'refs/heads/{b}' if b != '__default__' else None
            params.append(dict(commit_ids=commits, ref=ref))
        for t, commits in by_tags.items():
            ref = f'refs/tags/{t}'
            params.append(dict(commit_ids=commits, ref=ref))
        if params:
            RepoPushWebhookSender().send(params)

    log.info('Refresh complete for %s', repo.full_fs_path)
    g.post_event('repo_refreshed', len(commit_ids), all_commits, new_clone)

    # Send notifications
    if notify:
        send_notifications(repo, commit_ids)


def update_artifact_refs(commit, commit_ref):
    # very similar to add_artifacts() but works for Commit objects which aren't Artifacts
    if not commit.message:
        return
    shortlinks = find_shortlinks(commit.message)
    for link in shortlinks:
        artifact_ref = ArtifactReference.query.get(_id=link.ref_id)
        if artifact_ref and commit_ref._id not in artifact_ref.references:
            artifact_ref.references.append(commit_ref._id)
            log.info(f'Artifact references updated successfully {commit_ref._id} mentioned {link.ref_id}')


def refresh_commit_repos(all_commit_ids, repo):
    '''Refresh the list of repositories within which a set of commits are
    contained'''
    for oids in utils.chunked_iter(all_commit_ids, QSIZE):
        for ci in CommitDoc.m.find(dict(
                _id={'$in': list(oids)},
                repo_ids={'$ne': repo._id})):
            oid = ci._id
            ci.repo_ids.append(repo._id)
            index_id = 'allura.model.repository.Commit#' + oid
            # TODO: use ArtifactReference.from_artifact?
            ref = ArtifactReference(
                _id=index_id,
                artifact_reference=dict(
                    cls=bson.Binary(dumps(Commit, protocol=2)),
                    project_id=repo.app.config.project_id,
                    app_config_id=repo.app.config._id,
                    artifact_id=oid),
                references=[])
            # TODO: use Shortlink.from_artifact?
            link0 = Shortlink(
                _id=bson.ObjectId(),
                ref_id=index_id,
                project_id=repo.app.config.project_id,
                app_config_id=repo.app.config._id,
                link=repo.shorthand_for_commit(oid)[1:-1],
                url=repo.url_for_commit(oid))
            # Always create a link for the full commit ID
            link1 = Shortlink(
                _id=bson.ObjectId(),
                ref_id=index_id,
                project_id=repo.app.config.project_id,
                app_config_id=repo.app.config._id,
                link=oid,
                url=repo.url_for_commit(oid))
            ci.m.save(validate=False)

            update_artifact_refs(ci, ref)

            # set to 'dirty' to force save() to be used instead of insert() (which errors if doc exists in db already)
            state(ref).status = ObjectState.dirty
            session(ref).flush(ref)
            session(ref).expunge(ref)
            state(link0).status = ObjectState.dirty
            session(link0).flush(link0)
            session(link0).expunge(link0)
            state(link1).status = ObjectState.dirty
            session(link1).flush(link1)
            session(link1).expunge(link1)


def refresh_children(ci):
    '''Refresh the list of children of the given commit'''
    CommitDoc.m.update_partial(
        dict(_id={'$in': ci.parent_ids}),
        {'$addToSet': dict(child_ids=ci._id)},
        multi=True)


def unknown_commit_ids(all_commit_ids):
    '''filter out all commit ids that have already been cached'''
    result = []
    for chunk in utils.chunked_iter(all_commit_ids, QSIZE):
        chunk = list(chunk)
        q = CommitDoc.m.find(dict(_id={'$in': chunk}))
        known_commit_ids = {ci._id for ci in q}
        result += [oid for oid in chunk if oid not in known_commit_ids]
    return result


def send_notifications(repo, commit_ids):
    """Create appropriate notification and feed objects for a refresh

    :param repo: A repository artifact instance.
    :type repo: Repository

    :param commit_ids: A list of commit hash strings, oldest to newest
    :type commit_ids: list
    """
    from allura.model import Feed, Notification
    commit_msgs = []
    base_url = tg.config['base_url']
    for oids in utils.chunked_iter(commit_ids, QSIZE):
        chunk = list(oids)
        index = {
            doc._id: doc
            for doc in Commit.query.find(dict(_id={'$in': chunk}))}
        for oid in chunk:
            ci = index[oid]
            href = repo.url_for_commit(oid)
            title = _title(ci.message)
            summary = _summarize(ci.message)
            Feed.post(
                repo, title=title,
                description='{}<br><a href="{}">View Changes</a>'.format(
                    summary, href),
                author_link=ci.author_url,
                author_name=ci.authored.name,
                link=href,
                unique_id=href)

            summary = g.markdown_commit.convert(ci.message.strip()) if ci.message else ""
            current_branch = repo.symbolics_for_commit(ci)[0]  # only the head of a branch will have this
            commit_msgs.append(dict(
                author=ci.authored.name,
                date=ci.authored.date.strftime("%m/%d/%Y %H:%M"),
                summary=summary,
                branches=current_branch,
                commit_url=base_url + href,
                shorthand_id=ci.shorthand_id()))

    # fill out the branch info for all the other commits
    prev_branch = None
    for c_msg in reversed(commit_msgs):
        if not c_msg['branches']:
            c_msg['branches'] = prev_branch
        prev_branch = c_msg['branches']

    # mark which ones are first on a branch and need the branch name shown
    last_branch = None
    for c_msg in commit_msgs:
        if c_msg['branches'] != last_branch:
            c_msg['show_branch_name'] = True
        last_branch = c_msg['branches']

    if commit_msgs:
        if len(commit_msgs) > 1:
            subject = f"{len(commit_msgs)} new commits to {repo.app.config.options.mount_label}"
        else:
            commit = commit_msgs[0]
            subject = 'New commit {} by {}'.format(commit['shorthand_id'], commit['author'])
        text = g.jinja2_env.get_template("allura:templates/mail/commits.md").render(
            commit_msgs=commit_msgs,
            max_num_commits=asint(tg.config.get('scm.notify.max_commits', 100)),
        )

        Notification.post(
            artifact=repo,
            topic='metadata',
            subject=subject,
            text=text)


def _title(message):
    if not message:
        return ''
    line = message.splitlines()[0]
    return jinja2.filters.do_truncate(None, line, 200, killwords=True, leeway=3)


def _summarize(message):
    if not message:
        return ''
    summary = []
    for line in message.splitlines():
        line = line.rstrip()
        if line:
            summary.append(line)
        else:
            break
    return ' '.join(summary)


def last_known_commit_id(all_commit_ids, new_commit_ids):
    """
    Return the newest "known" (cached in mongo) commit id.

    Params:
        all_commit_ids: Every commit id from the repo on disk, sorted oldest to
                        newest.
        new_commit_ids: Commit ids that are not yet cached in mongo, sorted
                        oldest to newest.
    """
    if not all_commit_ids:
        return None
    if not new_commit_ids:
        return all_commit_ids[-1]
    return all_commit_ids[all_commit_ids.index(new_commit_ids[0]) - 1]


def _group_commits(repo, commit_ids):
    by_branches = {}
    by_tags = {}
    # svn has no branches, so we need __default__ as a fallback to collect
    # all commits into
    current_branches = ['__default__']
    current_tags = []
    for commit in commit_ids:
        ci = repo.commit(commit)
        branches, tags = repo.symbolics_for_commit(ci)
        if branches:
            current_branches = branches
        if tags:
            current_tags = tags
        for b in current_branches:
            if b not in list(by_branches.keys()):
                by_branches[b] = []
            by_branches[b].append(commit)
        for t in current_tags:
            if t not in list(by_tags.keys()):
                by_tags[t] = []
            by_tags[t].append(commit)
    return by_branches, by_tags
