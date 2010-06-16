from tg import expose, url, override_template
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import c

from pyforge.controllers import repository
from pyforge.lib.security import require, has_artifact_access

from .widgets import GitRevisionWidget

revision_widget = GitRevisionWidget()

def on_import():
    BranchBrowser.CommitBrowserClass = CommitBrowser
    CommitBrowser.TreeBrowserClass = TreeBrowser
    TreeBrowser.FileBrowserClass = FileBrowser

class BranchBrowser(repository.BranchBrowser):

    def _check_security(self):
        require(has_artifact_access('read', c.app.repo))

    @expose('forgegit.templates.index')
    @with_trailing_slash
    def index(self, offset=0, limit=10, **kw):
        c.revision_widget=revision_widget
        return dict(super(BranchBrowser, self).index(offset, limit),
                    allow_fork=True)

    @expose()
    def _lookup(self, rev, *remainder):
        return CommitBrowser(rev), remainder

class CommitBrowser(repository.CommitBrowser):
    revision_widget = GitRevisionWidget()

    def __init__(self, revision):
        super(CommitBrowser, self).__init__(None, revision)

    @expose('forgegit.templates.commit')
    @with_trailing_slash
    def index(self):
        result = super(CommitBrowser, self).index()
        c.revision_widget = revision_widget
        result.update(self._commit.context(self._branch))
        return result

class TreeBrowser(repository.TreeBrowser):

    @expose('forgegit.templates.tree')
    @with_trailing_slash
    def index(self):
        return super(TreeBrowser, self).index()

class FileBrowser(repository.FileBrowser):

    @expose('forgegit.templates.file')
    @without_trailing_slash
    def index(self, **kw):
        if 'diff' in kw:
            override_template(self.index, 'genshi:forgegit.templates.diff')
        return super(FileBrowser, self).index(**kw)

on_import()
