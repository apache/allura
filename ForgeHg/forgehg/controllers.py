from tg import expose, url, override_template, redirect
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import c

from allura.controllers import repository
from allura.lib.security import require, has_artifact_access
from allura.lib import patience

from .widgets import HgRevisionWidget, HgLog

revision_widget = HgRevisionWidget()
log_widget = HgLog()

def on_import():
    BranchBrowser.CommitBrowserClass = CommitBrowser
    CommitBrowser.TreeBrowserClass = TreeBrowser

class BranchBrowser(repository.BranchBrowser):

    def _check_security(self):
        require(has_artifact_access('read', c.app.repo))

    @expose('jinja:hg_index.html')
    @with_trailing_slash
    def index(self, limit=None, page=0, count=0, **kw):
        latest = c.app.repo.latest(branch=self._branch)
        if not latest:
            return dict(allow_fork=True, log=[])
        redirect(latest.tree().url())

    @expose('jinja:hg_log.html')
    @with_trailing_slash
    def log(self, limit=None, page=0, count=0, **kw):
        c.log_widget=log_widget
        return super(BranchBrowser, self).index(limit, page, count)

    @expose()
    def _lookup(self, rev, *remainder):
        return CommitBrowser(rev), remainder

class CommitBrowser(repository.CommitBrowser):
    revision_widget = HgRevisionWidget()

    @expose('jinja:hg_commit.html')
    @with_trailing_slash
    def index(self, **kw):
        result = super(CommitBrowser, self).index()
        c.revision_widget = revision_widget
        result.update(self._commit.context())
        return result

class TreeBrowser(repository.TreeBrowser):

    @expose('jinja:hg_tree.html')
    @with_trailing_slash
    def index(self, **kw):
        return super(TreeBrowser, self).index()

on_import()
