from tg import expose, redirect
from tg.decorators import with_trailing_slash
from pylons import tmpl_context as c

from allura.controllers import repository
from allura.lib import helpers as h

class BranchBrowser(repository.BranchBrowser):

    def __init__(self):
        super(BranchBrowser, self).__init__(None)

    @expose('jinja:forgesvn:templates/svn/index.html')
    @with_trailing_slash
    def index(self, limit=None, page=0, count=0, **kw):
        latest = c.app.repo.latest(branch=self._branch)
        if not latest or (latest._id.split(':')[1] == '1' and h.has_access(c.app, 'write')()):
            return dict(allow_fork=False, log=[])
        redirect(c.app.repo._impl.url_for_symbolic(latest._id) + 'tree/')

    @expose()
    def _lookup(self, rev, *remainder):
        return repository.CommitBrowser(rev), remainder

