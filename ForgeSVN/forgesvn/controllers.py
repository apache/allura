from tg import expose, url, override_template, redirect
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import c
from webob import exc

from allura.controllers import repository
from allura.lib.security import require, has_artifact_access

from .widgets import SVNRevisionWidget, SVNLog

revision_widget = SVNRevisionWidget()
log_widget = SVNLog()

def on_import():
    BranchBrowser.CommitBrowserClass = CommitBrowser
    CommitBrowser.TreeBrowserClass = TreeBrowser
    TreeBrowser.FileBrowserClass = FileBrowser

class BranchBrowser(repository.BranchBrowser):

    def _check_security(self):
        require(has_artifact_access('read', c.app.repo))

    def __init__(self):
        super(BranchBrowser, self).__init__(None)

    @expose('jinja:svn_index.html')
    @with_trailing_slash
    def index(self):
        latest = c.app.repo.latest
        if not latest:
            return dict(log=[])
        redirect(c.app.url+"LATEST/tree/")

    @expose('jinja:svn_log.html')
    @with_trailing_slash
    def log(self, limit=None, page=0, count=0, **kw):
        c.log_widget=log_widget
        return super(BranchBrowser, self).index(limit, page, count)

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
        try:
            rev = int(rev)
        except ValueError:
            raise exc.HTTPNotFound()
        super(CommitBrowser, self).__init__(rev)

    @expose('jinja:svn_commit.html')
    @with_trailing_slash
    def index(self, **kw):
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

    @expose('jinja:svn_tree.html')
    @with_trailing_slash
    def index(self, **kw):
        return super(TreeBrowser, self).index()

class FileBrowser(repository.FileBrowser):

    @expose('jinja:svn_file.html')
    @without_trailing_slash
    def index(self, **kw):
        if 'diff' in kw:
            override_template(self.index, 'jinja:svn_diff.html')
            return self.diff(int(kw['diff']))
        result = super(FileBrowser, self).index(**kw)
        return result

on_import()
