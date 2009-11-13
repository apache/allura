import logging

import pylons
from pylons import c
import pkg_resources
from webob import exc

from ming import Document, Session, Field, datastore
from ming import schema as S

log = logging.getLogger(__name__)

class ProjectSession(Session):

    def __init__(self, main_session):
        self.main_session = main_session

    def _impl(self, cls):
        db = getattr(self.main_session.bind.conn, c.project.database)
        return db[cls.__mongometa__.name]

class Project(Document):
    class __mongometa__:
        session = Session.by_name('main')
        name='project'

    # Project schema
    _id=Field(str)
    name=Field(str)
    database=Field(str)
    is_root=Field(bool)
    members=Field([
            dict(
                id=int,
                uname=str,
                display=str)])

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
    def direct_subprojects(self):
        depth = self._id.count('/')
        for sp in self.subprojects:
            if sp._id.count('/') - depth == 1:
                yield sp

    @property
    def project_bind(self):
        return datastore.DataStore(self.dburi)

    def install_app(self, ep_name):
        for ep in pkg_resources.iter_entry_points('pyforge', ep_name):
            App = ep.load()
            break
        else:
            raise exc.HTTPNotFound, ep_name
        config = App.default_config
        cfg = AppConfig.make(dict(project_id=self._id,
                                  name=ep_name,
                                  config=config))
        app = App(cfg)
        c.app = app
        app.install(self)
        cfg.m.save()
        return app

    def uninstall_app(self, app_name):
        app = self.app_instance(app_name)
        if app is None: return
        app.uninstall(self)
        app.config.m.delete()

    def app_instance(self, app_name):
        app_config = self.app_config(app_name)
        if app_config is None:
            return None
        for ep in pkg_resources.iter_entry_points('pyforge', app_name):
            App = ep.load()
            return App(app_config)
        else:
            return None

    def app_config(self, app_name):
        return AppConfig.m.get(project_id=self._id, name=app_name)


    def new_subproject(self, name):
        sp = self.make(dict(
                _id = self._id + name + '/',
                dburi=self.dburi,
                is_root=False,
                members=self.members))
        sp.m.save()
        return sp

    def delete(self):
        # Cascade to subprojects
        for sp in self.subprojects:
            sp.m.delete()
        self.m.delete()

class AppConfig(Document):
    class __mongometa__:
        session = ProjectSession(Session.by_name('main'))
        name='config'

    # AppConfig schema
    _id=Field(S.ObjectId)
    project_id=Field(str)
    name=Field(str)
    version=Field(str)
    config=Field(None)

class Artifact(Document):
    class __mongometa__:
        session = ProjectSession(Session.by_name('main'))
        name='artifact'

    # Artifact base schema
    _id = Field(S.ObjectId)
    project_id = Field(S.String, if_missing=lambda:c.project._id)
    plugin_verson = Field(
        S.Object,
        { str: str },
        if_missing=lambda:{c.app.config.name:c.app.__version__})
    acl = Field(
        S.Object,
        dict(
            read=[str],
            write=[str],
            delete=[str],
            comment=[str]),
        if_missing=dict(
            read=['*anonymous', '*authenticated'],
            write=['*authenticated'],
            delete=['*authenticated'],
            comment=['*anonymous', '*authenticated']))

    def has_access(self, access_type):
        roles = [ '*anonymous' ]
        # Add other roles based on the username and groups
        acl = set(self.acl[access_type])
        for r in roles:
            if r in acl: return True
        return False
