import difflib
from pprint import pformat

import pkg_resources
from pylons import c, request
from tg import expose, redirect, validate
from tg.decorators import with_trailing_slash
from formencode import validators as V

from pyforge.app import Application, ConfigOption, SitemapEntry
from pyforge import version
from pyforge.model import ProjectRole
from pyforge.lib.helpers import push_config
from pyforge.lib.security import require, has_artifact_access
from pyforge.lib import search

class SearchApp(Application):
    '''This is the HelloWorld application for PyForge, showing
    all the rich, creamy goodness that is installable apps.
    '''
    __version__ = version.__version__
    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = SearchController()

    @property
    def sitemap(self):
        return [SitemapEntry('Search Project', '.')]

    def sidebar_menu(self):
        return [ ]

    @property
    def templates(self):
        return pkg_resources.resource_filename('pyforge.ext.search', 'templates')

    def install(self, project):
        pass

    def uninstall(self, project):
        pass

class SearchController(object):

    @expose('pyforge.templates.search_index')
    @validate(dict(q=V.UnicodeString(),
                   history=V.StringBool(if_empty=False)))
    @with_trailing_slash
    def index(self, q=None, history=None):
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
            search_query = '%s AND is_history_b:%s AND (%s)' % (
                q, history, project_match)
            results = search.search(search_query, is_history_b=history)
            if results: count=results.hits
        return dict(q=q, history=history, results=results or [], count=count)

