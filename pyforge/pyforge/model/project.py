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
            'security':[S.ObjectId],  # update ACL, roles
            })

    def sidebar_menu(self):
        from pyforge.app import SitemapEntry
        result = []
        if not self.is_root:
            p = self.parent_project
            result.append(SitemapEntry('Parent Project'))
            result.append(SitemapEntry(p.name or p.script_name, p.script_name))
        sps = self.direct_subprojects
        if sps:
            result.append(SitemapEntry('Child Projects'))
            result += [
                SitemapEntry(p.name or p.script_name, p.script_name)
                for p in sps ]
        return result

    @property
    def script_name(self):
        return '/' + self._id
            
    @property
    def shortname(self):
        return self._id.split('/')[-2]

    @property
    def parent_project(self):
        if self.is_root: return None
        parent_id, shortname, empty = self._id.rsplit('/', 2)
        return self.m.get(_id=parent_id + '/')

    def sitemap(self):
        from pyforge.app import SitemapEntry
        sitemap = SitemapEntry('root')
        for ac in self.app_configs:
            App = ac.load()
            app = App(self, ac)
            app_sitemap = [ sm.bind_app(app) for sm in app.sitemap ]
            sitemap.extend(app_sitemap)
        return sitemap.children

    def parent_iter(self):
        yield self
        pp = self.parent_project
        if pp:
            for p in pp.parent_iter():
                yield p

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

    @property
    def app_configs(self):
        return AppConfig.m.find(dict(project_id=self._id)).all()

    @property
    def roles(self):
        from . import auth
        roles = auth.ProjectRole.m.find().all()
        return sorted(roles, key=lambda r:r.display())

    def install_app(self, ep_name, mount_point):
        for ep in pkg_resources.iter_entry_points('pyforge', ep_name):
            App = ep.load()
            break
        else:
            raise exc.HTTPNotFound, ep_name
        options = App.default_options()
        options['mount_point'] = mount_point
        cfg = AppConfig.make(dict(
                project_id=self._id,
                plugin_name=ep_name,
                options=options,
                acl=dict((p,[]) for p in App.permissions)))
        app = App(self, cfg)
        c.project = self
        cfg.m.save()
        c.app = app
        app.install(self)
        c.app = None
        return app

    def uninstall_app(self, mount_point):
        app = self.app_instance(mount_point)
        if app is None: return
        app.uninstall(self)
        app.config.m.delete()

    def app_instance(self, mount_point):
        app_config = self.app_config(mount_point)
        if app_config is None:
            return None
        App = app_config.load()
        if App is None:
            return None
        else:
            return App(self, app_config)

    def app_config(self, mount_point):
        return AppConfig.m.find({
                'project_id':self._id,
                'options.mount_point':mount_point}).first()

    def new_subproject(self, name):
        sp = self.make(dict(
                _id = self._id + name + '/',
                database=self.database,
                is_root=False,
                acl=self.acl))
        sp.install_app('admin', 'admin')
        sp.install_app('search', 'search')
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
    plugin_name=Field(str)
    version=Field(str)
    options=Field(None)

    acl = Field({str:[S.ObjectId]}) # acl[permission] = [ role1, role2, ... ]

    @property
    def project(self):
        return Project.m.get(_id=self.project_id)
    
    def load(self):
        for ep in pkg_resources.iter_entry_points(
            'pyforge', self.plugin_name):
            return ep.load()
        return None
