import logging
from ming import Document, Session

log = logging.getLogger(__name__)

class Project(Document):
    class __mongometa__:
        session = Session.by_name('main')
        name='project'
        _member = dict(
            id=int,
            uname=str,
            display=str)
        _app = dict(
            name=str,
            version=str,
            )
        schema=dict(
            _id=str,
            members=[_member],
            apps=[_app])
