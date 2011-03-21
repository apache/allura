import logging

from pylons import c

from ming import Session
from ming.datastore import ShardedDataStore
from ming.orm.base import state, session
from ming.orm.ormsession import ThreadLocalORMSession, SessionExtension

log = logging.getLogger(__name__)

class ProjectSession(Session):

    def __init__(self, main_session):
        self.main_session = main_session

    @property
    def db(self):
        try:
            assert c.project.database_uri
            scheme, rest = c.project.database_uri.split('://')
            host, database = rest.split('/', 1)
            return ShardedDataStore.get(scheme + '://' + host, database).db
        except (KeyError, AttributeError, TypeError), ex:
            return None

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
        "Update artifact references, and add/update this artifact to solr"
        import allura.tasks.index_tasks
        if not getattr(self.session, 'disable_artifact_index', False):
            from .stats import CPA
            from .index import ArtifactReference
            from .session import main_orm_session
            # Ensure artifact references exist for new objects
            for obj in self.objects_added:
                ArtifactReference.from_artifact(obj)
            # Post delete and add indexing operations
            if self.objects_deleted:
                allura.tasks.index_tasks.del_artifacts.post(
                    [ obj.index_id() for obj in self.objects_deleted ])
            if self.objects_added or self.objects_modified:
                allura.tasks.index_tasks.add_artifacts.post(
                    [ obj.index_id() for obj in self.objects_added + self.objects_modified ])
            # Flush tasks
            main_orm_session.flush()
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
