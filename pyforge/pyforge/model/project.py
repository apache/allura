import logging
import pylons
from ming import Document, Session, datastore
from ming import schema as S


log = logging.getLogger(__name__)

class ProjectSession(object):

    @property
    def _impl(self):
        return Session(bind=pylons.c.project.project_bind)

    def __getattr__(self, name):
        return getattr(self._impl, name)

class Project(Document):
    class __mongometa__:
        session = Session.by_name('main')
        name='project'
        _member = dict(
            id=int,
            uname=str,
            display=str)
        schema=dict(
            _id=str,
            name=str,
            dburi=str,
            is_root=bool,
            members=[_member])

    @property
    def shortname(self):
        return self._id.split('/')[-2]

    @property
    def subprojects(self):
        q = self.m.find(dict(_id={'$gt':self._id}))
        for project in q:
            if project._id.startswith(self._id):
                yield project
            else:
                break

    @property
    def project_bind(self):
        return datastore.DataStore(self.dburi)

    def app_config(self, app_name):
        return AppConfig.m.get(project_id=self._id, name=app_name)

class AppConfig(Document):
    class __mongometa__:
        session = ProjectSession()
        name='config'
        schema=dict(
            _id=S.ObjectId(),
            project_id=str,
            name=str,
            config=None)
            
        
