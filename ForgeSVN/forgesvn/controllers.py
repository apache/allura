from tg import expose, url, override_template
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import c

from pyforge.controllers import repository
from pyforge.lib.security import require, has_artifact_access

from .widgets import SVNRevisionWidget

revision_widget = SVNRevisionWidget()

def on_import():
    BranchBrowser.CommitBrowserClass = CommitBrowser
    CommitBrowser.TreeBrowserClass = TreeBrowser
    TreeBrowser.FileBrowserClass = FileBrowser

class BranchBrowser(repository.BranchBrowser):

    def _check_security(self):
        require(has_artifact_access('read', c.app.repo))

    def __init__(self):
        super(BranchBrowser, self).__init__(None)

    @expose('forgesvn.templates.index')
    @with_trailing_slash
    def index(self, offset=0, limit=10):
        c.revision_widget=revision_widget
        return super(BranchBrowser, self).index(offset, limit)
        offset=int(offset)
        repo = c.app.repo
        if repo and repo.status=='ready':
            revisions = repo.log(offset=offset, limit=10)
        else:
            revisions = []
        c.revision_widget=revision_widget
        next_link = url(dict(offset=offset+10))
        return dict(
            repo=c.app.repo,
            revisions=revisions,
            next_link=next_link)

    @expose()
    def _lookup(self, rev, *remainder):
        return CommitBrowser(rev), remainder

class CommitBrowser(repository.CommitBrowser):
    revision_widget = SVNRevisionWidget()

    def __init__(self, rev):
        if rev == 'LATEST':
            if c.app.repo.latest:
                rev = c.app.repo.latest.revision.number
            else:
                rev = 0
        super(CommitBrowser, self).__init__(int(rev))

    @expose('forgesvn.templates.commit')
    @with_trailing_slash
    def index(self):
        result = super(CommitBrowser, self).index()
        if not self._commit:
            return result
        if self._revision > 1:
            result['prev'] = '../%s/' % (self._revision - 1)
        else:
            result['prev'] = None
        if self._revision < c.app.repo.latest.revision.number:
            result['next'] = '../%s/' % (self._revision + 1)
        else:
            result['next'] = None
        c.revision_widget = revision_widget
        return result

class TreeBrowser(repository.TreeBrowser):

    @expose('forgesvn.templates.tree')
    @with_trailing_slash
    def index(self):
        return super(TreeBrowser, self).index()

class FileBrowser(repository.FileBrowser):

    @expose('forgesvn.templates.file')
    @without_trailing_slash
    def index(self, **kw):
        if 'diff' in kw:
            override_template(self.index, 'genshi:forgesvn.templates.diff')
            return self.diff(int(kw['diff']))
        result = super(FileBrowser, self).index(**kw)
        return result

on_import()
