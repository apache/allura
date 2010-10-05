import os
import logging
from urllib import unquote

from pylons import c, g, request, response
import tg
from tg import redirect, expose, url, override_template
from tg.decorators import with_trailing_slash

from allura.lib import patience
from allura.lib.widgets.file_browser import TreeWidget
from allura import model
from .base import BaseController

log = logging.getLogger(__name__)

def on_import():
    BranchBrowser.CommitBrowserClass = CommitBrowser
    CommitBrowser.TreeBrowserClass = TreeBrowser
    TreeBrowser.FileBrowserClass = FileBrowser

class BranchBrowser(BaseController):
    CommitBrowserClass=None

    def __init__(self, branch):
        self._branch = branch

    def index(self, limit=None, page=0, count=0, **kw):
        limit, page, start = g.handle_paging(limit, page)
        count = c.app.repo.count(branch=self._branch)
        revisions = c.app.repo.log(
                branch=self._branch,
                offset=start,
                limit=limit)
        return dict(
            username=c.user._id and c.user.username,
            branch=self._branch,
            log=revisions,
            page=page,
            limit=limit,
            count=count,
            **kw)

    @expose()
    def _lookup(self, commit, *rest):
        commit=unquote(commit)
        return self.CommitBrowserClass(commit), rest

class CommitBrowser(BaseController):
    TreeBrowserClass=None
    revision_widget = None

    def __init__(self, revision):
        self._revision = revision
        self._commit = c.app.repo.commit(revision)
        self.tree = self.TreeBrowserClass(self._commit, tree=self._commit.tree)

    def index(self):
        c.revision_widget = self.revision_widget
        result = dict(commit=self._commit)
        if self._commit:
            result.update(self._commit.context())
        return result

class TreeBrowser(BaseController):
    FileBrowserClass=None
    tree_widget=TreeWidget()

    def __init__(self, commit, tree, path='', parent=None):
        self._commit = commit
        self._tree = tree
        self._path = path + '/'
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
            filename = request.environ['PATH_INFO'].rsplit('/')[-1]
            if filename and self._tree.is_blob(filename):
                return self.FileBrowserClass(
                    self._commit,
                    self._tree,
                    filename), rest
        elif rest == ('index', ):
            rest = (request.environ['PATH_INFO'].rsplit('/')[-1],)
        return self.__class__(
            self._commit,
            self._tree.get_tree(next),
            self._path + next,
            self), rest

class FileBrowser(BaseController):

    def __init__(self, commit, tree, filename):
        self._commit = commit
        self._tree = tree
        self._filename = filename
        self._blob = self._tree.get_blob(filename)

    @expose('jinja:repo/file.html')
    def index(self, **kw):
        self._blob.context()
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
            a_tree = a_ci.tree
            a = a_tree.get_blob(filename, path[1:].split('/'))
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
