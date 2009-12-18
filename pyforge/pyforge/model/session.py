from pylons import c
from ming import Session
from ming.orm.ormsession import ThreadLocalORMSession, SessionExtension

from pyforge.lib import search

class ProjectSession(Session):

    def __init__(self, main_session):
        self.main_session = main_session

    def _impl(self, cls):
        db = getattr(self.main_session.bind.conn, c.project.database)
        return db[cls.__mongometa__.name]

class ArtifactSessionExtension(SessionExtension):

    def __init__(self, session):
        SessionExtension.__init__(self, session)
        self.objects_removed = []

    def after_insert(self, obj, st):
        from .artifact import ArtifactLink
        search.add_artifact(obj)
        ArtifactLink.add(obj)

    def after_update(self, obj, st):
        from .artifact import ArtifactLink
        search.add_artifact(obj)
        ArtifactLink.add(obj)

    def after_delete(self, obj, st):
        from .artifact import ArtifactLink
        search.remove_artifact(obj)
        ArtifactLink.remove(obj)

    def before_remove(self, cls, *args, **kwargs):
        from .artifact import ArtifactLink
        self.objects_removed = [
            (obj, state(obj)) for obj in cls.query.find(*args, **kwargs) ]

    def after_remove(self, cls, *args, **kwargs):
        for obj, st in self.objects_removed:
            self.after_delete(obj, st)
        self.objects_removed = []

main_doc_session = Session.by_name('main')
project_doc_session = ProjectSession(main_doc_session)
main_orm_session = ThreadLocalORMSession(main_doc_session)
project_orm_session = ThreadLocalORMSession(project_doc_session)
artifact_orm_session = ThreadLocalORMSession(
    doc_session=project_doc_session,
    extensions = [ ArtifactSessionExtension ])
