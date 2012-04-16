import logging

import pkg_resources
from pylons import c
from tg import expose, validate
from tg.decorators import with_trailing_slash
from formencode import validators as V

from allura.app import Application
from allura import version
from allura.lib import search
from allura.controllers import BaseController

log = logging.getLogger(__name__)

class SearchApp(Application):
    '''This is the HelloWorld application for Allura, showing
    all the rich, creamy goodness that is installable apps.
    '''
    __version__ = version.__version__
    installable = False
    sitemap=[]
    
    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = SearchController()
        self.templates = pkg_resources.resource_filename('allura.ext.search', 'templates')

    def main_menu(self): # pragma no cover
        return []

    def sidebar_menu(self): # pragma no cover
        return [ ]

    def admin_menu(self): # pragma no cover
        return []

    def install(self, project):
        pass # pragma no cover

    def uninstall(self, project):
        pass # pragma no cover

class SearchController(BaseController):

    @expose('jinja:allura:templates/search_index.html')
    @validate(dict(q=V.UnicodeString(),
                   history=V.StringBool(if_empty=False)))
    @with_trailing_slash
    def index(self, q=None, history=None, **kw):
        results = []
        count=0
        if not q:
            q = ''
        else:
            pids = [c.project._id] + [
                p._id for p in c.project.subprojects ]
            project_match = ' OR '.join(
                'project_id_s:%s' % pid
                for pid in pids )
            search_query = '%s AND is_history_b:%s AND (%s) AND -deleted_b:true' % (
                q, history, project_match)
            results = search.search(search_query, is_history_b=history)
            if results: count=results.hits
        return dict(q=q, history=history, results=results or [], count=count)

