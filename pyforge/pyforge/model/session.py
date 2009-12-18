from pylons import c
from ming import Session
from ming.orm.ormsession import ThreadLocalORMSession
from ming.orm.ormsession import ORMSession

class ProjectSession(Session):

    def __init__(self, main_session):
        self.main_session = main_session

    def _impl(self, cls):
        db = getattr(self.main_session.bind.conn, c.project.database)
        return db[cls.__mongometa__.name]

class ProjectORMSession(ORMSession):

    def __init__(self, main_session):
        ORMSession.__init__(self)
        self.impl = ProjectSession(main_session.impl)

main_doc_session = Session.by_name('main')
project_doc_session = ProjectSession(main_doc_session)
main_orm_session = ThreadLocalORMSession(main_doc_session)
project_orm_session = ThreadLocalORMSession(main_orm_session)

