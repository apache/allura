import logging
from datetime import datetime, timedelta

from pylons import c, g
import pkg_resources
from webob import exc
from pymongo import bson

from ming import Document, Session, Field, datastore
from ming import schema as S

from pyforge.lib.helpers import push_config
from .session import ProjectSession

log = logging.getLogger(__name__)

class SearchConfig(Document):
    class __mongometa__:
        session = Session.by_name('main')
        name='search_config'

    _id = Field(S.ObjectId)
    last_commit = Field(datetime, if_missing=datetime.min)
    pending_commit = Field(int, if_missing=0)

    def needs_commit(self):
        now = datetime.utcnow()
        elapsed = now - self.last_commit
        td_threshold = timedelta(seconds=60)
        return elapsed > td_threshold and self.pending_commit

class ScheduledMessage(Document):
    class __mongometa__:
        session = Session.by_name('main')
        name='scheduled_message'

    _id = Field(S.ObjectId)
    when = Field(datetime)
    exchange = Field(str)
    routing_key = Field(str)
    data = Field(None)
    nonce = Field(S.ObjectId, if_missing=None)

    @classmethod
    def fire_when_ready(cls):
        now = datetime.utcnow()
        # Lock the objects to fire
        nonce = bson.ObjectId()
        cls.m.update_partial({'when' : { '$lt':now},
                              'nonce': None },
                             {'$set': {'nonce':nonce}})
        # Actually fire
        for obj in cls.m.find(dict(nonce=nonce)):
            log.info('Firing scheduled message to %s:%s',
                     obj.exchange, obj.routing_key)
            try:
                g.publish(obj.exchange, obj.routing_key, obj.get('data'))
                obj.m.delete()
            except:
                log.exception('Error when firing %r', obj)

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

    def install_app(self, ep_name, mount_point, **override_options):
        assert self.app_instance(mount_point) is None
        for ep in pkg_resources.iter_entry_points('pyforge', ep_name):
            App = ep.load()
            break
        else:
            raise exc.HTTPNotFound, ep_name
        options = App.default_options()
        options['mount_point'] = mount_point
        options.update(override_options)
        cfg = AppConfig.make(dict(
                project_id=self._id,
                plugin_name=ep_name,
                options=options,
                acl=dict((p,[]) for p in App.permissions)))
        app = App(self, cfg)
        with push_config(c, project=self, app=app):
            cfg.m.save()
            app.install(self)
        return app

    def uninstall_app(self, mount_point):
        app = self.app_instance(mount_point)
        if app is None: return
        app.uninstall(self)
        app.config.m.delete()

    def app_instance(self, mount_point_or_config):
        if isinstance(mount_point_or_config, AppConfig):
            app_config = mount_point_or_config
        else:
            app_config = self.app_config(mount_point_or_config)
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

    def new_subproject(self, name, install_apps=True):
        sp = self.make(dict(
                _id = self._id + name + '/',
                database=self.database,
                is_root=False))
        if install_apps:
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
