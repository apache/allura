import os
import json
import logging
from urllib import quote, unquote
from collections import defaultdict

from pylons import c, g, request, response
from webob import exc
import tg
from tg import redirect, expose, flash, url, validate
from tg.decorators import with_trailing_slash, without_trailing_slash
from formencode import validators
from bson import ObjectId
from ming.orm import ThreadLocalORMSession, session

import allura.tasks
from allura.lib import patience
from allura.lib import security
from allura.lib import helpers as h
from allura.lib import widgets as w
from allura.lib.decorators import require_post
from allura.controllers import AppDiscussionController
from allura.lib.widgets.repo import SCMLogWidget, SCMRevisionWidget, SCMTreeWidget
from allura.lib.widgets.repo import SCMMergeRequestWidget, SCMMergeRequestFilterWidget
from allura.lib.widgets.repo import SCMMergeRequestDisposeWidget, SCMCommitBrowserWidget
from allura import model as M

from .base import BaseController

log = logging.getLogger(__name__)

def on_import():
    BranchBrowser.CommitBrowserClass = CommitBrowser
    CommitBrowser.TreeBrowserClass = TreeBrowser
    TreeBrowser.FileBrowserClass = FileBrowser

class RepoRootController(BaseController):
    _discuss = AppDiscussionController()
    commit_browser_widget=SCMCommitBrowserWidget()

    def _check_security(self):
        security.require(security.has_access(c.app, 'read'))

    @with_trailing_slash
    @expose()
    def index(self, offset=0, branch=None, **kw):
        if branch is None:
            branch=c.app.default_branch_name
        redirect(url(quote('%s%s/' % (
                        branch, c.app.END_OF_REF_ESCAPE))))

    @expose()
    def refresh(self):
        allura.tasks.repo_tasks.refresh.post()
        if request.referer:
            flash('Repository is being refreshed')
            redirect(request.referer)
        else:
            return '%r refresh queued.\n' % c.app.repo

    @with_trailing_slash
    @expose('jinja:allura:templates/repo/fork.html')
    def fork(self, to_name=None, project_id=None):
        # this shows the form and handles the submission
        security.require_authenticated()
        if not c.app.forkable: raise exc.HTTPNotFound
        from_repo = c.app.repo
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        from_project = c.project
        to_project = M.Project.query.get(_id=ObjectId(project_id))
        if request.method != 'POST' or not to_name:
            return dict(from_repo=from_repo,
                        user_project=c.user.private_project(),
                        to_name=to_name or '')
        else:
            with h.push_config(c, project=to_project):
                if not to_project.database_configured:
                    to_project.configure_project(is_user_project=True)
                security.require(security.has_access(to_project, 'admin'))
                try:
                    to_project.install_app(
                        from_repo.tool_name, to_name,
                        cloned_from_project_id=from_project._id,
                        cloned_from_repo_id=from_repo._id)
                    redirect(to_project.url()+to_name+'/')
                except exc.HTTPRedirection:
                    raise
                except Exception, ex:
                    flash(str(ex), 'error')
                    redirect(request.referer)

    @property
    def mr_widget(self):
        source_branches = [
            b.name
            for b in c.app.repo.branches + c.app.repo.repo_tags]
        with c.app.repo.push_upstream_context():
            target_branches = [
                b.name
                for b in c.app.repo.branches + c.app.repo.repo_tags]
        return SCMMergeRequestWidget(
            source_branches=source_branches,
            target_branches=target_branches)

    @without_trailing_slash
    @expose('jinja:allura:templates/repo/request_merge.html')
    def request_merge(self, branch=None):
        security.require(security.has_access(c.app.repo, 'admin'))
        c.form = self.mr_widget
        if branch is None:
            source_branch=c.app.repo.branches[0].name
        return dict(source_branch=source_branch)

    @expose()
    @require_post()
    def do_request_merge(self, **kw):
        kw = self.mr_widget.to_python(kw)
        downstream=dict(
            project_id=c.project._id,
            mount_point=c.app.config.options.mount_point,
            commit_id=c.app.repo.commit(kw['source_branch']).object_id)
        with c.app.repo.push_upstream_context():
            mr = M.MergeRequest.upsert(
                downstream=downstream,
                target_branch=kw['target_branch'],
                summary=kw['summary'],
                description=kw['description'])
            M.Notification.post(
                mr, 'merge_request',
                subject='Merge request: ' + mr.summary)
            t = M.Thread(
                discussion_id=c.app.config.discussion_id,
                artifact_reference=mr.index_id(),
                subject='Discussion for Merge Request #:%s: %s' % (
                    mr.request_number, mr.summary))
            session(t).flush()
            redirect(mr.url())

    @without_trailing_slash
    @expose()
    @validate(dict(
            since=h.DateTimeConverter(if_empty=None, if_invalid=None),
            until=h.DateTimeConverter(if_empty=None, if_invalid=None),
            offset=validators.Int(if_empty=None),
            limit=validators.Int(if_empty=None)))
    def feed(self, since=None, until=None, offset=None, limit=None):
        if request.environ['PATH_INFO'].endswith('.atom'):
            feed_type = 'atom'
        else:
            feed_type = 'rss'
        title = 'Recent changes to %s' % c.app.config.options.mount_point
        feed = M.Feed.feed(
            dict(project_id=c.project._id,app_config_id=c.app.config._id),
            feed_type,
            title,
            c.app.url,
            title,
            since, until, offset, limit)
        response.headers['Content-Type'] = ''
        response.content_type = 'application/xml'
        return feed.writeString('utf-8')

    @without_trailing_slash
    @expose('jinja:allura:templates/repo/commit_browser.html')
    def commit_browser(self):
        if not c.app.repo or c.app.repo.status != 'ready':
            return dict(status='not_ready')
        # if c.app.repo.count() > 2000:
        #     return dict(status='too_many_commits')
        if c.app.repo.count() == 0:
            return dict(status='no_commits')
        c.commit_browser_widget = self.commit_browser_widget
        return dict(status='ready')

    @without_trailing_slash
    @expose('json:')
    def commit_browser_data(self):
        head_ids = [ head.object_id for head in c.app.repo.heads ]
        commit_ids = list(M.repo.commitlog(head_ids))
        log.info('Grab %d commit objects by ID', len(commit_ids))
        commits_by_id = dict(
            (c_obj._id, c_obj)
            for c_obj in M.repo.CommitDoc.m.find(dict(_id={'$in': commit_ids})))
        log.info('... build graph')
        parents = {}
        children = defaultdict(list)
        dates = {}
        for row, (oid, ci) in enumerate(commits_by_id.iteritems()):
            parents[oid] = list(ci.parent_ids)
            dates[oid] = ci.committed.date
            for p_oid in ci.parent_ids:
                children[p_oid].append(oid)
        result = []
        for row, oid in enumerate(topo_sort(children, parents, dates, head_ids)):
            ci = commits_by_id[oid]
            result.append(dict(
                    oid=oid,
                    row=row,
                    parents=ci.parent_ids,
                    message=ci.message.splitlines()[0],
                    url='#'))
        log.info('...done')
        col_idx = {}
        columns = []
        for row, ci_json in enumerate(result):
            oid = ci_json['oid']
            colno = len(columns)
            chs = children[oid]
            for ch in chs:
                ch_col = col_idx.get(ch, None)
                if columns[ch_col] == ch:
                    colno = min(colno, ch_col)
            col_idx[oid] = ci_json['column'] = colno
            while colno >= len(columns):
                columns.append(None)
            columns[colno] = oid
        built_tree = dict(
                (ci_json['oid'], ci_json) for ci_json in result)
        return dict(
            commits=[ ci_json['oid'] for ci_json in result ],
            built_tree=built_tree,
            next_column=len(columns),
            max_row=row)

class RepoRestController(RepoRootController):
    @expose('json:')
    def index(self, **kw):
        all_commits = c.app.repo._impl.new_commits(all_commits=True)
        return dict(commit_count=len(all_commits))

    @expose('json:')
    def commits(self, **kw):
        page_size = 25
        offset = (int(kw.get('page',1)) * page_size) - page_size
        revisions = c.app.repo.log(offset=offset, limit=page_size)

        return dict(
            commits=[
                dict(
                    parents=[dict(id=p) for p in commit.parent_ids],
                    author=dict(
                        name=commit.authored.name,
                        email=commit.authored.email,
                    ),
                    url=commit.url(),
                    id=commit.object_id,
                    committed_date=commit.committed.date,
                    authored_date=commit.authored.date,
                    message=commit.message,
                    tree=commit.tree.object_id,
                    committer=dict(
                        name=commit.committed.name,
                        email=commit.committed.email,
                    ),
                )
            for commit in revisions
        ])

class MergeRequestsController(object):
    mr_filter=SCMMergeRequestFilterWidget()

    @expose('jinja:allura:templates/repo/merge_requests.html')
    @validate(mr_filter)
    def index(self, status=None):
        status = status or ['open']
        requests = c.app.repo.merge_requests_by_statuses(*status)
        c.mr_filter = self.mr_filter
        return dict(
            status=status,
            requests=requests)

    @expose()
    def _lookup(self, num, *remainder):
        return MergeRequestController(num), remainder

class MergeRequestController(object):
    log_widget=SCMLogWidget()
    thread_widget=w.Thread(
        page=None, limit=None, page_size=None, count=None,
        style='linear')
    mr_dispose_form=SCMMergeRequestDisposeWidget()

    def __init__(self, num):
        self.req = M.MergeRequest.query.get(
            app_config_id=c.app.config._id,
            request_number=int(num))
        if self.req is None: raise exc.HTTPNotFound

    @expose('jinja:allura:templates/repo/merge_request.html')
    def index(self, page=0, limit=250):
        c.thread = self.thread_widget
        c.log_widget = self.log_widget
        c.mr_dispose_form = self.mr_dispose_form
        return dict(
            req=self.req,
            page=page,
            limit=limit,
            count=self.req.discussion_thread.post_count)

    @expose()
    @require_post()
    @validate(mr_dispose_form)
    def save(self, status=None):
        security.require(
            security.has_access(self.req, 'write'), 'Write access required')
        self.req.status = status
        redirect('.')


class RefsController(object):

    def __init__(self, BranchBrowserClass):
        self.BranchBrowserClass = BranchBrowserClass

    @expose()
    def _lookup(self, *parts):
        parts = map(unquote, parts)
        ref = []
        while parts:
            part = parts.pop(0)
            ref.append(part)
            if part.endswith(c.app.END_OF_REF_ESCAPE):
                break
        ref = '/'.join(ref)[:-1]
        return self.BranchBrowserClass(ref), parts

class CommitsController(object):

    @expose()
    def _lookup(self, ci, *remainder):
        return CommitBrowser(ci), remainder

class BranchBrowser(BaseController):
    CommitBrowserClass=None

    def __init__(self, branch):
        self._branch = branch

    def _check_security(self):
        security.require(security.has_access(c.app.repo, 'read'))

    @expose('jinja:allura:templates/repo/tags.html')
    @with_trailing_slash
    def tags(self, **kw):
        return dict(tags=c.app.repo.repo_tags)

    @expose()
    @with_trailing_slash
    def log(self, **kw):
        ci = c.app.repo.commit(self._branch)
        redirect(ci.url() + 'log/')

class CommitBrowser(BaseController):
    TreeBrowserClass=None
    revision_widget = SCMRevisionWidget()
    log_widget=SCMLogWidget()

    def __init__(self, revision):
        self._revision = revision
        self._commit = c.app.repo.commit(revision)
        if self._commit is None:
            raise exc.HTTPNotFound
        self.tree = self.TreeBrowserClass(self._commit, tree=self._commit.tree)

    @expose('jinja:allura:templates/repo/commit.html')
    def index(self):
        c.revision_widget = self.revision_widget
        result = dict(commit=self._commit)
        if self._commit:
            result.update(self._commit.context())
        return result

    @expose('jinja:allura:templates/repo/commit_basic.html')
    def basic(self):
        c.revision_widget = self.revision_widget
        result = dict(commit=self._commit)
        if self._commit:
            result.update(self._commit.context())
        return result

    @expose('jinja:allura:templates/repo/log.html')
    @with_trailing_slash
    def log(self, limit=None, page=0, count=0, **kw):
        limit, page, start = g.handle_paging(limit, page)
        revisions = c.app.repo.log(
                branch=self._commit.object_id,
                offset=start,
                limit=limit)
        c.log_widget = self.log_widget
        count = 0
        return dict(
            username=c.user._id and c.user.username,
            branch=None,
            log=revisions,
            page=page,
            limit=limit,
            count=count,
            **kw)

class TreeBrowser(BaseController):
    tree_widget = SCMTreeWidget()
    FileBrowserClass=None

    def __init__(self, commit, tree, path='', parent=None):
        self._commit = commit
        self._tree = tree
        self._path = path
        self._parent = parent

    @expose('jinja:allura:templates/repo/tree.html')
    @with_trailing_slash
    def index(self, **kw):
        c.tree_widget = self.tree_widget
        return dict(
            repo=c.app.repo,
            commit=self._commit,
            tree=self._tree,
            path=self._path,
            parent=self._parent)

    @expose()
    def _lookup(self, next, *rest):
        next=unquote(next)
        if not rest:
            # Might be a file rather than a dir
            filename = h.really_unicode(
                unquote(
                    request.environ['PATH_INFO'].rsplit('/')[-1]))
            if filename and filename in self._tree.object_id_index and self._tree.is_blob(filename):
                return self.FileBrowserClass(
                    self._commit,
                    self._tree,
                    filename), rest
        elif rest == ('index', ):
            rest = (request.environ['PATH_INFO'].rsplit('/')[-1],)
        tree = self._tree.get_tree(next)
        if tree is None:
            raise exc.HTTPNotFound
        return self.__class__(
            self._commit,
            tree,
            self._path + '/' + next,
            self), rest

class FileBrowser(BaseController):

    def __init__(self, commit, tree, filename):
        self._commit = commit
        self._tree = tree
        self._filename = filename
        self._blob = self._tree.get_blob(filename)

    @expose('jinja:allura:templates/repo/file.html')
    def index(self, **kw):
        if kw.pop('format', 'html') == 'raw':
            return self.raw()
        elif 'diff' in kw:
            tg.decorators.override_template(self.index, 'jinja:allura:templates/repo/diff.html')
            return self.diff(kw['diff'])
        else:
            force_display = 'force' in kw
            context = self._blob.context()
            return dict(
                blob=self._blob,
                prev=context.get('prev', None),
                next=context.get('next', None),
                force_display=force_display
                )

    @expose()
    def raw(self):
        content_type = self._blob.content_type.encode('utf-8')
        filename = self._blob.name.encode('utf-8')
        response.headers['Content-Type'] = ''
        response.content_type = content_type
        if self._blob.content_encoding is not None:
            content_encoding = self._blob.content_encoding.encode('utf-8')
            response.headers['Content-Encoding'] = ''
            response.content_encoding = content_encoding
        response.headers.add(
            'Content-Disposition', 'attachment;filename=' + filename)
        return iter(self._blob)

    def diff(self, commit):
        try:
            path, filename = os.path.split(self._blob.path())
            a_ci = c.app.repo.commit(commit)
            a = a_ci.get_path(self._blob.path())
            apath = a.path()
        except:
            a = []
            apath = ''
        b = self._blob
        la = list(a)
        lb = list(b)
        diff = ''.join(patience.unified_diff(
                la, lb,
                ('a' + apath).encode('utf-8'),
                ('b' + b.path()).encode('utf-8')))
        return dict(
            a=a, b=b,
            diff=diff)

def topo_sort(children, parents, dates, head_ids):
    to_visit = set(head_ids)
    visited = set()
    while to_visit:
        next = max(to_visit, key=lambda x: dates[x])
        to_visit.remove(next)
        if next in visited: continue
        visited.add(next)
        yield next
        for p in parents[next]:
            for c in children[p]:
                if c not in visited: break
            else:
                to_visit.add(p)

on_import()
