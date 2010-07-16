from tg import expose, url, override_template
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import c

from pyforge.controllers import repository
from pyforge.lib.security import require, has_artifact_access
from pyforge.lib import patience

from .widgets import GitRevisionWidget

revision_widget = GitRevisionWidget()

def on_import():
    BranchBrowser.CommitBrowserClass = CommitBrowser

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

    @expose('forgegit.templates.commit')
    @with_trailing_slash
    def index(self, **kw):
        return super(CommitBrowser, self).index()

on_import()
