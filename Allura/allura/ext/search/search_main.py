import difflib
import logging
from datetime import datetime, timedelta
from pprint import pformat

import pkg_resources
from pylons import c, g, request
from tg import expose, redirect, validate
from tg.decorators import with_trailing_slash
from formencode import validators as V

from allura.app import Application, ConfigOption, SitemapEntry
from allura import version
from allura.model import ProjectRole, SearchConfig, ScheduledMessage, Project
from allura.lib.security import require, has_artifact_access
from allura.lib.decorators import audit, react
from allura.lib import search
from allura.lib import helpers as h
from allura import model as M
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

    @classmethod
    @react('artifacts_altered')
    def add_artifacts(cls, routing_key, doc):
        log.info('Adding %d artifacts', len(doc['artifacts']))
        obj = SearchConfig.query.find().first()
        obj.pending_commit += len(doc['artifacts'])
        artifacts = [ ref.artifact for ref in doc['artifacts'] if ref.artifact ]
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
                a = M.ArtifactReference(r.artifact_reference).artifact
                if a is None: continue
                a.backreferences[s['id']] =aref
        # TODO: maybe move to the top of function?
        M.session.artifact_orm_session._get().skip_mod_date = True
        M.session.artifact_orm_session._get().disable_artifact_index = True

    @classmethod
    @react('artifacts_removed')
    def del_artifacts(cls, routing_key, doc):
        log.info('Removing %d artifacts', len(doc['artifacts']))
        obj = SearchConfig.query.find().first()
        obj.pending_commit += len(doc['artifacts'])
        artifacts = ( ref.artifact for ref in doc['artifacts'] if ref is not None and ref.artifact is not None )
        artifacts = ((a, search.solarize(a)) for a in artifacts)
        artifacts = [ (a, s) for a,s in artifacts if s is not None ]
        # Add to solr
        g.solr.delete([ s for a,s in artifacts])
        # Add backreferences
        for a, s in artifacts:
            c.app = c.project.app_instance(a.app_config)
            for r in search.find_shortlinks(s['text']):
                a = M.ArtifactReference(r.artifact_reference).artifact
                if a is None: continue
                del a.backreferences[s['id']]
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

class SearchController(BaseController):

    @expose('jinja:search_index.html')
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
            search_query = '%s AND is_history_b:%s AND (%s)' % (
                q, history, project_match)
            results = search.search(search_query, is_history_b=history)
            if results: count=results.hits
        return dict(q=q, history=history, results=results or [], count=count)

