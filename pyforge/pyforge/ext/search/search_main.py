import difflib
import logging
from datetime import datetime, timedelta
from pprint import pformat

import pkg_resources
from pylons import c, g, request
from tg import expose, redirect, validate
from tg.decorators import with_trailing_slash
from formencode import validators as V

from pyforge.app import Application, ConfigOption, SitemapEntry
from pyforge import version
from pyforge.model import ProjectRole, SearchConfig, ScheduledMessage
from pyforge.lib.helpers import push_config
from pyforge.lib.security import require, has_artifact_access
from pyforge.lib.decorators import audit
from pyforge.lib import search

log = logging.getLogger(__name__)

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

    @classmethod
    @audit('search.add_artifacts')
    def add_artifacts(cls, routing_key, doc):
        obj = SearchConfig.m.find().first()
        for a in doc['artifacts']:
            log.info('Adding artifact: %s', a['id'])
            obj.pending_commit += 1
        g.solr.add(doc['artifacts'])

    @classmethod
    @audit('search.del_artifacts')
    def del_artifacts(cls, routing_key, doc):
        for aid in doc['artifact_ids']:
            log.info('Removing artifact: %s', aid)
            g.solr.delete(id=aid)

    @classmethod
    @audit('search.check_commit')
    def check_commit(cls, routing_key, doc):
        log.info('Checking commits')
        obj = SearchConfig.m.find().first()
        now = datetime.utcnow()
        if obj.needs_commit():
            log.info('Committing to solr')
            obj.last_commit = now
            obj.pending_commit = 0
            obj.m.save()
            g.solr.commit()
        ScheduledMessage.make(dict(
                when=now+timedelta(seconds=60),
                exchange='audit',
                routing_key='search.check_commit')).m.save()
                                   
        

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

