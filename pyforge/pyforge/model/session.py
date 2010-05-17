import logging
from itertools import chain

from pylons import c

from ming import Session
from ming.orm.base import state, session
from ming.orm.ormsession import ThreadLocalORMSession, SessionExtension

from pyforge.lib import search
from pyforge.lib.custom_middleware import environ

log = logging.getLogger(__name__)

class ProjectSession(Session):

    def __init__(self, main_session):
        self.main_session = main_session

    @property
    def db(self):
        try:
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
            return getattr(self.main_session.bind.conn, p.database)
        except (KeyError, AttributeError), ex:
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
        self.objects_deleted = []

    def before_flush(self, obj=None):
        if obj is None:
            self.objects_added = list(
                chain(self.session.uow.new,
                      self.session.uow.dirty))
            self.objects_deleted = list(self.session.uow.deleted)
        else: # pragma no cover
            st = state(obj)
            if st.status in (st.new, st.dirty):
                self.objects_added = [ obj ]
            elif st.status == st.deleted:
                self.objects_deleted = [ obj ]

    def after_flush(self, obj=None):
        if not getattr(self.session, 'disable_artifact_index', False):
            from .artifact import ArtifactLink
            if self.objects_deleted:
                search.remove_artifacts(self.objects_deleted)
                for obj in self.objects_deleted:
                    ArtifactLink.remove(obj)
            if self.objects_added:
                search.add_artifacts(self.objects_added)
                for obj in self.objects_added:
                    try:
                        ArtifactLink.add(obj)
                    except:
                        log.exception('Error adding ArtifactLink for %s', obj)
                session(ArtifactLink).flush()
        self.objects_added = []
        self.objects_deleted = []

main_doc_session = Session.by_name('main')
project_doc_session = ProjectSession(main_doc_session)
main_orm_session = ThreadLocalORMSession(main_doc_session)
project_orm_session = ThreadLocalORMSession(project_doc_session)
artifact_orm_session = ThreadLocalORMSession(
    doc_session=project_doc_session,
    extensions = [ ArtifactSessionExtension ])
