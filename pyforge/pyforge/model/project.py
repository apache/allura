import logging

from pylons import c
import pkg_resources
from webob import exc

from ming import Document, Session, Field, datastore
from ming import schema as S

from .session import ProjectSession

log = logging.getLogger(__name__)

class Project(Document):
    class __mongometa__:
        session = Session.by_name('main')
        name='project'

    # Project schema
    _id=Field(str)
    name=Field(str)
    database=Field(str)
    is_root=Field(bool)
    acl = Field({
            'create':[S.ObjectId],    # create subproject
            'read':[S.ObjectId],      # read project
            'delete':[S.ObjectId],    # delete project, subprojects
            'plugin':[S.ObjectId],    # install/delete/configure plugins
            'security':[S.ObjectId],  # update ACL
            })

    def allow_user(self, user, *permissions):
        for p in permissions:
            acl = set(self.acl[p])
            acl.add(user._id)
            self.acl[p] = list(acl)

    def deny_user(self, user, *permissions):
        for p in permissions:
            acl = set(self.acl[p])
            acl.discard(user._id)
            self.acl[p] = list(acl)
            
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
                acl=self.acl))
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

    permissions=Field([str])
    acl = Field({str:[str]}) # acl[permission] = [ role1, role2, ... ]

