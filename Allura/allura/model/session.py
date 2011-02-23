import logging

from pylons import c

from ming import Session
from ming.datastore import ShardedDataStore
from ming.orm.base import state, session
from ming.orm.ormsession import ThreadLocalORMSession, SessionExtension

from allura.lib import search
from allura.lib.custom_middleware import environ

log = logging.getLogger(__name__)

class ProjectSession(Session):

    def __init__(self, main_session):
        self.main_session = main_session

    @property
    def db(self):
        try:
            p = self.project
            if p.database_uri:
                scheme, rest = p.database_uri.split('://')
                host, database = rest.split('/', 1)
                return ShardedDataStore.get(scheme + '://' + host, database).db
            return getattr(self.main_session.bind.conn, p.database)
        except (KeyError, AttributeError), ex:
            return None

    @property
    def project(self):
        # Our MagicalC makes sure allura.project is set in the environ when
        # c.project is set
        p = environ.get('allura.project', None)
        if p is None:
            # But if we're not using MagicalC, as in paster shell....
            try:
                p = getattr(c, 'project', None)
            except TypeError:
                 # running without MagicalC, inside a request (likely EasyWidgets)
                return None
        if p is None: return None
        return p

    def _impl(self, cls):
        db = self.db
        if db:
            return db[cls.__mongometa__.name]
        else: # pragma no cover
            return None

class ArtifactSessionExtension(SessionExtension):

    def __init__(self, session):
        SessionExtension.__init__(self, session)
        self.objects_added = []
        self.objects_modified = []
        self.objects_deleted = []

    def before_flush(self, obj=None):
        if obj is None:
            self.objects_added = list(self.session.uow.new)
            self.objects_modified = list(self.session.uow.dirty)
            self.objects_deleted = list(self.session.uow.deleted)
        else: # pragma no cover
            st = state(obj)
            if st.status == st.new:
                self.objects_added = [ obj ]
            elif st.status == st.dirty:
                self.objects_modified = [ obj ]
            elif st.status == st.deleted:
                self.objects_deleted = [ obj ]

    def after_flush(self, obj=None):
        if not getattr(self.session, 'disable_artifact_index', False):
            from .artifact import ArtifactLink
            from .stats import CPA
            if self.objects_deleted:
                search.remove_artifacts(self.objects_deleted)
                for obj in self.objects_deleted:
                    ArtifactLink.remove(obj)
            to_update = self.objects_added + self.objects_modified
            if to_update:
                search.add_artifacts(to_update)
                for obj in to_update:
                    try:
                        ArtifactLink.add(obj)
                    except:
                        log.exception('Error adding ArtifactLink for %s', obj)
                session(ArtifactLink).flush()
            for obj in self.objects_added:
                CPA.post('create', obj)
            for obj in self.objects_modified:
                CPA.post('modify', obj)
            for obj in self.objects_deleted:
                CPA.post('delete', obj)
        self.objects_added = []
        self.objects_modified = []
        self.objects_deleted = []

main_doc_session = Session.by_name('main')
project_doc_session = ProjectSession(main_doc_session)
main_orm_session = ThreadLocalORMSession(main_doc_session)
project_orm_session = ThreadLocalORMSession(project_doc_session)
artifact_orm_session = ThreadLocalORMSession(
    doc_session=project_doc_session,
    extensions = [ ArtifactSessionExtension ])
repository_orm_session = ThreadLocalORMSession(
    doc_session=main_doc_session,
    extensions = [  ])
