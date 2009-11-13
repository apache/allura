from pylons import c
from ming import Session

class ProjectSession(Session):

    def __init__(self, main_session):
        self.main_session = main_session

    def _impl(self, cls):
        db = getattr(self.main_session.bind.conn, c.project.database)
        return db[cls.__mongometa__.name]

