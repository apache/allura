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
from pyforge.model import ProjectRole, SearchConfig, ScheduledMessage, Project
from pyforge.lib.helpers import push_config
from pyforge.lib.security import require, has_artifact_access
from pyforge.lib.decorators import audit, react
from pyforge.lib import search
from pyforge import model as M

log = logging.getLogger(__name__)

class SearchApp(Application):
    '''This is the HelloWorld application for PyForge, showing
    all the rich, creamy goodness that is installable apps.
    '''
    __version__ = version.__version__
    installable = False
    sitemap=[]
    
    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = SearchController()
        self.templates = pkg_resources.resource_filename('pyforge.ext.search', 'templates')

    @classmethod
    @react('artifacts_altered')
    def add_artifacts(cls, routing_key, doc):
        log.info('Adding %d artifacts', len(doc['artifacts']))
        obj = SearchConfig.query.find().first()
        obj.pending_commit += len(doc['artifacts'])
        artifacts = ( ref.to_artifact() for ref in doc['artifacts'] )
        artifacts = ((a, search.solarize(a)) for a in artifacts)
        artifacts = [ (a, s) for a,s in artifacts if s is not None ]
        # Add to solr
        g.solr.add([ s for a,s in artifacts])
        # Add backreferences
        for a, s in artifacts:
            if isinstance(a, M.Snapshot): continue
            c.app = c.project.app_instance(a.app_config)
            aref = a.dump_ref()
            references = list(search.find_shortlinks(s['text']))
            a.references = [ r.artifact_reference for r in references ]
            for r in references:
                M.ArtifactReference(r.artifact_reference).to_artifact().backreferences[s['id']] =aref
        M.session.artifact_orm_session._get().disable_artifact_index = True

    @classmethod
    @react('artifacts_removed')
    def del_artifacts(cls, routing_key, doc):
        log.info('Removing %d artifacts', len(doc['artifacts']))
        obj = SearchConfig.query.find().first()
        obj.pending_commit += len(doc['artifacts'])
        artifacts = ( ref.to_artifact() for ref in doc['artifacts'] if ref is not None)
        artifacts = ((a, search.solarize(a)) for a in artifacts)
        artifacts = [ (a, s) for a,s in artifacts if s is not None ]
        # Add to solr
        g.solr.delete([ s for a,s in artifacts])
        # Add backreferences
        for a, s in artifacts:
            c.app = c.project.app_instance(a.app_config)
            for r in search.find_shortlinks(s['text']):
                del M.ArtifactReference(r.artifact_reference).to_artifact().backreferences[s['id']]
        M.session.artifact_orm_session._get().disable_artifact_index = True

    @classmethod
    @audit('search.check_commit')
    def check_commit(cls, routing_key, doc):
        obj = SearchConfig.query.find().first()
        now = datetime.utcnow()
        if obj.needs_commit():
            obj.last_commit = now
            obj.pending_commit = 0
            g.solr.commit()
        ScheduledMessage(
            when=now+timedelta(seconds=60),
            exchange='audit',
            routing_key='search.check_commit')

    def sidebar_menu(self):
        return [ ]

    def admin_menu(self):
        return []

    def install(self, project):
        pass # pragma no cover

    def uninstall(self, project):
        pass # pragma no cover

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

