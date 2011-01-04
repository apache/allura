import os
import logging
from urllib import quote, unquote

from pylons import c, g, request, response
from webob import exc
from tg import redirect, expose, override_template, flash, url, validate
from tg.decorators import with_trailing_slash, without_trailing_slash

from ming.orm import ThreadLocalORMSession, session

from allura.lib import patience
from allura.lib import security
from allura.lib import helpers as h
from allura.lib import widgets as w
from allura.controllers import AppDiscussionController
from allura.lib.widgets.repo import SCMLogWidget, SCMRevisionWidget, SCMTreeWidget
from allura.lib.widgets.repo import SCMMergeRequestWidget, SCMMergeRequestFilterWidget
from allura.lib.widgets.repo import SCMMergeRequestDisposeWidget
from allura import model as M

from .base import BaseController

log = logging.getLogger(__name__)

def on_import():
    BranchBrowser.CommitBrowserClass = CommitBrowser
    CommitBrowser.TreeBrowserClass = TreeBrowser
    TreeBrowser.FileBrowserClass = FileBrowser

class RepoRootController(BaseController):
    _discuss = AppDiscussionController()

    def _check_security(self):
        security.require(security.has_artifact_access('read'))

    @expose()
    def index(self, offset=0, branch=None, **kw):
        if branch is None:
            branch=c.app.default_branch_name
        redirect(url(quote('%s%s/' % (
                        branch, c.app.END_OF_REF_ESCAPE))))

    @expose()
    def refresh(self):
        g.publish('audit', 'repo.refresh')
        return '%r refresh queued.\n' % c.app.repo

    @with_trailing_slash
    @expose('jinja:repo/fork.html')
    def fork(self, to_name=None, project_name=None):
        security.require_authenticated()
        if not c.app.forkable: raise exc.HTTPNotFound
        from_repo = c.app.repo
        if project_name:
            to_project_name = project_name
        else:
            to_project_name = 'u/' + c.user.username
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        from_project = c.project
        to_project = M.Project.query.get(shortname=to_project_name)
        with h.push_config(c, project=to_project):
            if request.method!='POST' or to_name is None:
                if to_project is None:
                    in_use = []
                    to_project_name = ''
                else:
                    prefix_len = len(to_project_name+'/')
                    in_use = [sp.shortname[prefix_len:] for sp in to_project.direct_subprojects]
                    in_use += [ac.options['mount_point'] for ac in to_project.app_configs]
                return dict(from_repo=from_repo,
                            to_project_name=to_project_name,
                            in_use=in_use,
                            to_name=to_name or '')
            else:
                if not to_project.database_configured:
                    to_project.configure_project(is_user_project=True)
                security.require(security.has_project_access('tool', to_project))
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
            for b in c.app.repo.branches + c.app.repo.tags]
        with c.app.repo.push_upstream_context():
            target_branches = [
                b.name
                for b in c.app.repo.branches + c.app.repo.tags]
        return SCMMergeRequestWidget(
            source_branches=source_branches,
            target_branches=target_branches)

    @without_trailing_slash
    @expose('jinja:repo/request_merge.html')
    def request_merge(self, branch=None):
        c.form = self.mr_widget
        if branch is None:
            source_branch=c.app.repo.branches[0].name
        return dict(source_branch=source_branch)

    @expose()
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
            t = M.Thread(
                discussion_id=c.app.config.discussion_id,
                artifact_reference=mr.dump_ref(),
                subject='Discussion for Merge Request #:%s: %s' % (
                    mr.request_number, mr.summary))
            session(t).flush()
            redirect(mr.url())

class MergeRequestsController(object):
    mr_filter=SCMMergeRequestFilterWidget()

    @expose('jinja:repo/merge_requests.html')
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
            request_number=int(num))
        if self.req is None: raise exc.HTTPNotFound

    @expose('jinja:repo/merge_request.html')
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
    @validate(mr_dispose_form)
    def save(self, status=None):
        security.require(
            security.has_artifact_access('write', self.req), 'Write access required')
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
        security.require(security.has_artifact_access('read', c.app.repo))

    @expose('jinja:repo/tags.html')
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
        self.tree = self.TreeBrowserClass(self._commit, tree=self._commit.tree)

    @expose('jinja:repo/commit.html')
    def index(self):
        c.revision_widget = self.revision_widget
        result = dict(commit=self._commit)
        if self._commit:
            result.update(self._commit.context())
        return result

    @expose('jinja:repo/log.html')
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

    @expose('jinja:repo/tree.html')
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
            if filename and self._tree.is_blob(filename):
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

    @expose('jinja:repo/file.html')
    def index(self, **kw):
        if kw.pop('format', 'html') == 'raw':
            return self.raw()
        elif 'diff' in kw:
            override_template(self.index, 'jinja:repo/diff.html')
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

on_import()
