import logging
import warnings
from datetime import datetime, timedelta

from pylons import c, g, request
import pkg_resources
from webob import exc
from pymongo import bson

from ming import Document, Session, Field, datastore
from ming.orm.base import mapper, session
from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty, RelationProperty, ForeignIdProperty
from ming import schema as S

from pyforge.lib.helpers import push_config
from .session import main_doc_session, main_orm_session
from .session import project_doc_session, project_orm_session

log = logging.getLogger(__name__)

class SearchConfig(MappedClass):
    class __mongometa__:
        session = main_orm_session
        name='search_config'

    _id = FieldProperty(S.ObjectId)
    last_commit = FieldProperty(datetime, if_missing=datetime.min)
    pending_commit = FieldProperty(int, if_missing=0)

    def needs_commit(self):
        now = datetime.utcnow()
        elapsed = now - self.last_commit
        td_threshold = timedelta(seconds=60)
        return elapsed > td_threshold and self.pending_commit

class ScheduledMessage(MappedClass):
    class __mongometa__:
        session = main_orm_session
        name='scheduled_message'

    _id = FieldProperty(S.ObjectId)
    when = FieldProperty(datetime)
    exchange = FieldProperty(str)
    routing_key = FieldProperty(str)
    data = FieldProperty(None)
    nonce = FieldProperty(S.ObjectId, if_missing=None)

    @classmethod
    def fire_when_ready(cls):
        now = datetime.utcnow()
        # Lock the objects to fire
        nonce = bson.ObjectId()
        m = mapper(cls)
        session(cls).impl.update_partial(
            m.doc_cls,
            {'when' : { '$lt':now},
             'nonce': None },
            {'$set': {'nonce':nonce}},
            False)
        # Actually fire
        for obj in cls.query.find(dict(nonce=nonce)):
            log.info('Firing scheduled message to %s:%s',
                     obj.exchange, obj.routing_key)
            try:
                g.publish(obj.exchange, obj.routing_key, getattr(obj, 'data', None))
                obj.delete()
            except:
                log.exception('Error when firing %r', obj)

class Project(MappedClass):
    class __mongometa__:
        session = main_orm_session
        name='project'

    # Project schema
    _id=FieldProperty(str)
    name=FieldProperty(str)
    short_description=FieldProperty(str, if_missing='')
    description=FieldProperty(str, if_missing='')
    database=FieldProperty(str)
    is_root=FieldProperty(bool)
    acl = FieldProperty({
            'create':[S.ObjectId],    # create subproject
            'read':[S.ObjectId],      # read project
            'update':[S.ObjectId],    # update project metadata
            'delete':[S.ObjectId],    # delete project, subprojects
            'plugin':[S.ObjectId],    # install/delete/configure plugins
            'security':[S.ObjectId],  # update ACL, roles
            })
    app_configs = RelationProperty('AppConfig')


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
        warnings.warn('script_name is deprecated, use url() instead',
                      DeprecationWarning, stacklevel=2)
        if ':/' in self._id:
            domain, path = self._id.split(':/', 1)
            return '/' + path
        return '/' + self._id

    def url(self):
        if ':/' in self._id:
            domain, path = self._id.split(':/', 1)
            try:
                if ':' in request.host:
                    port = request.host.split(':')[-1]
                    return '%s://%s:%s/%s' % (
                        request.scheme, domain, port, path)
                else:
                    return '%s://%s/%s' % (request.scheme, domain, path)
            except TypeError:
                return 'http://%s/%s' % (domain, path)
            return '/' + path
        return '/' + self._id

    @property
    def shortname(self):
        return self._id.split('/')[-2]

    @property
    def description_html(self):
        return g.markdown.convert(self.description)

    @property
    def parent_project(self):
        if self.is_root: return None
        parent_id, shortname, empty = self._id.rsplit('/', 2)
        return self.query.get(_id=parent_id + '/')

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
        q = self.query.find(dict(_id={'$gt':self._id}))
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
    def roles(self):
        from . import auth
        roles = auth.ProjectRole.query.find().all()
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
        cfg = AppConfig(
            project_id=self._id,
            plugin_name=ep_name,
            options=options,
            acl=dict((p,[]) for p in App.permissions))
        app = App(self, cfg)
        with push_config(c, project=self, app=app):
            session(cfg).flush()
            app.install(self)
        return app

    def uninstall_app(self, mount_point):
        app = self.app_instance(mount_point)
        if app is None: return
        with push_config(c, project=self, app=app):
            app.uninstall(self)
        app.config.delete()

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
        return AppConfig.query.find({
                'project_id':self._id,
                'options.mount_point':mount_point}).first()

    def new_subproject(self, name, install_apps=True):
        _id = self._id + name + '/'
        sp = Project(
            _id=_id,
            name=name,
            database=self.database,
            is_root=False)
        if install_apps:
            sp.install_app('admin', 'admin')
            sp.install_app('search', 'search')
        return sp

    def delete(self):
        # Cascade to subprojects
        for sp in self.subprojects:
            sp.delete()
        MappedClass.delete(self)

    def render_widget(self, widget):
        app = self.app_instance(widget['mount_point'])
        with push_config(c, project=self, app=app):
            return getattr(app.widget(app), widget['widget_name'])()

    def breadcrumbs(self):
        entry = ( self.name, self.url() )
        if self.parent_project:
            return self.parent_project.breadcrumbs() + [ entry ]
        else:
            return [ ( self._id.rsplit('/', 2)[0], None) ] + [ entry ]

class AppConfig(MappedClass):
    class __mongometa__:
        session = project_orm_session
        name='config'

    # AppConfig schema
    _id=FieldProperty(S.ObjectId)
    project_id=ForeignIdProperty(Project)
    plugin_name=FieldProperty(str)
    version=FieldProperty(str)
    options=FieldProperty(None)
    project = RelationProperty(Project, via='project_id')


    # acl[permission] = [ role1, role2, ... ]
    acl = FieldProperty({str:[S.ObjectId]}) 

    def load(self):
        for ep in pkg_resources.iter_entry_points(
            'pyforge', self.plugin_name):
            return ep.load()
        return None

    def script_name(self):
        warnings.warn('script_name is deprecated, use url() instead',
                      DeprecationWarning, stacklevel=2)
        return self.project.script_name + self.options.mount_point + '/'

    def url(self):
        return self.project.url() + self.options.mount_point + '/'

    def breadcrumbs(self):
        return self.project.breadcrumbs() + [
            (self.options.mount_point, self.url()) ]
            
