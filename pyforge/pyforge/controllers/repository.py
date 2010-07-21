import os
from urllib import unquote

from pylons import c, request, response
from tg import redirect, expose, url, override_template

from pyforge.lib import patience
from pyforge.lib.widgets.file_browser import TreeWidget
from pyforge import model

def on_import():
    BranchBrowser.CommitBrowserClass = CommitBrowser
    CommitBrowser.TreeBrowserClass = TreeBrowser
    TreeBrowser.FileBrowserClass = FileBrowser

class BranchBrowser(object):
    CommitBrowserClass=None

    def __init__(self, branch):
        self._branch = branch

    def index(self, limit=None, page=0, count=0, **kw):
        if limit:
            if c.user in (None, model.User.anonymous()):
                tg.session['results_per_page'] = int(limit)
                tg.session.save()
            else:
                c.user.preferences.results_per_page = int(limit)
        else:
            if c.user in (None, model.User.anonymous()):
                limit = 'results_per_page' in tg.session and tg.session['results_per_page'] or 50
            else:
                limit = c.user.preferences.results_per_page or 50
        page = max(int(page), 0)
        start = page * int(limit)
        count = c.app.repo.count(branch=self._branch)
        revisions = c.app.repo.log(
                branch=self._branch,
                offset=start,
                limit=limit)
        revisions = [ dict(value=r) for r in revisions ]
        for r in revisions:
            r.update(r['value'].context())
        return dict(
            username=c.user._id and c.user.username,
            branch=self._branch,
            log=revisions,
            page=page,
            limit=limit,
            count=count)

    @expose()
    def _lookup(self, commit, *rest):
        commit=unquote(commit)
        return self.CommitBrowserClass(commit), rest

class CommitBrowser(object):
    TreeBrowserClass=None
    revision_widget = None

    def __init__(self, revision):
        self._revision = revision
        self._commit = c.app.repo.commit(revision)
        self.tree = self.TreeBrowserClass(self._commit)

    def index(self):
        c.revision_widget = self.revision_widget
        result = dict(commit=self._commit)
        if self._commit:
            result.update(self._commit.context())
        return result

class TreeBrowser(object):
    FileBrowserClass=None
    tree_widget=TreeWidget()

    def __init__(self, commit, parent=None, name=None):
        self._commit = commit
        self._parent = parent
        self._name = name
        if parent:
            self._tree = parent.get_tree(name)
        elif self._commit:
            self._tree = self._commit.tree()
        else:
            self._tree = None

    @expose('pyforge.templates.repo.tree')
    def index(self):
        c.tree_widget = self.tree_widget
        return dict(
            commit=self._commit,
            tree=self._tree,
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
        return self.__class__(
            self._commit,
            self._tree,
            next), rest

class FileBrowser(object):

    def __init__(self, commit, tree, filename):
        self._commit = commit
        self._tree = tree
        self._filename = filename
        self._blob = self._tree.get_blob(filename)

    @expose('pyforge.templates.repo.file')
    def index(self, **kw):
        self._blob.context()
        if kw.pop('format', 'html') == 'raw':
            return self.raw()
        elif 'diff' in kw:
            override_template(self.index, 'genshi:pyforge.templates.repo.diff')
            return self.diff(kw['diff'])
        else:
            context = self._blob.context()
            return dict(
                blob=self._blob,
                prev=context.get('prev', None),
                next=context.get('next', None)
                )

    @expose()
    def raw(self):
        content_type = self._blob.content_type.encode('utf-8')
        filename = self._blob.filename.encode('utf-8')
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
            a_tree = a_ci.tree()
            a = a_tree.get_blob(filename, path[1:].split('/'))
        except:
            a = []
        b = self._blob
        la = list(a)
        lb = list(b)
        diff = ''.join(patience.unified_diff(
                la, lb,
                'a' + a.path(), 'b' + b.path()))
        return dict(
            a=a, b=b,
            diff=diff)

on_import()
