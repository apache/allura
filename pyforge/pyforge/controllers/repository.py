from urllib import unquote

from pylons import c, request, response
from tg import redirect, expose, url

from pyforge.lib import patience
from pyforge.lib.widgets.file_browser import TreeWidget

def on_import():
    BranchBrowser.CommitBrowserClass = CommitBrowser
    CommitBrowser.TreeBrowserClass = TreeBrowser
    TreeBrowser.FileBrowserClass = FileBrowser

class BranchBrowser(object):
    CommitBrowserClass=None

    def __init__(self, branch):
        self._branch = branch

    def index(self, offset=0, limit=10):
        offset=int(offset)
        limit=int(limit)
        next_link = url('.', dict(offset=offset+10))
        return dict(
            username=c.user._id and c.user.username,
            branch=self._branch,
            next_link=next_link,
            log=c.app.repo.log(
                branch=self._branch,
                offset=offset,
                limit=limit))

    @expose()
    def _lookup(self, commit, *rest):
        commit=unquote(commit)
        return self.CommitBrowserClass(commit), rest

class CommitBrowser(object):
    TreeBrowserClass=None

    def __init__(self, branch, revision):
        self._branch = branch
        self._revision = revision
        self._commit = c.app.repo.commit(branch, revision)
        self.tree = self.TreeBrowserClass(self._branch, self._commit)

    def index(self):
        return dict(
            branch=self._branch,
            commit=self._commit)

class TreeBrowser(object):
    FileBrowserClass=None
    tree_widget=TreeWidget()

    def __init__(self, branch, commit, parent=None, name=None):
        self._branch = branch
        self._commit = commit
        self._parent = parent
        self._name = name
        if parent:
            self._tree = parent.get_tree(name)
        else:
            self._tree = self._commit.tree(
                self._branch)

    def index(self):
        c.tree_widget = self.tree_widget
        return dict(
            branch=self._branch,
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
                    self._branch,
                    self._commit,
                    self._tree,
                    filename), rest
        return self.__class__(
            self._branch,
            self._commit,
            self._tree,
            next), rest

class FileBrowser(object):

    def __init__(self, branch, commit, tree, filename):
        self._branch = branch
        self._commit = commit
        self._tree = tree
        self._filename = filename
        self._blob = self._tree.get_blob(filename)

    def index(self, **kw):
        self._blob.context(self._branch)
        if kw.pop('format', 'html') == 'raw':
            return self.raw()
        elif 'diff' in kw:
            return self.diff()
        else:
            context = self._blob.context(self._branch)
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

    def diff(self):
        d = self._blob.context(self._branch)
        a = d['prev']
        b = self._blob
        la=list(a)
        lb=list(b)
        # differ = patience.SequenceMatcher(None, la, lb)
        # opcodes = differ.get_opcodes()
        diff = ''.join(patience.unified_diff(
                la, lb,
                'a' + a.path(), 'b' + b.path()))
        return dict(
            a=a, b=b,
            diff=diff)
