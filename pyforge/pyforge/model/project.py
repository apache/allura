import logging
import warnings
from datetime import datetime, timedelta

from pylons import c, g, request
import pkg_resources
from webob import exc
from pymongo import bson

from ming import schema as S
from ming.orm.base import mapper, session
from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty, RelationProperty, ForeignIdProperty
from ming.orm.ormsession import ThreadLocalORMSession

from pyforge.lib import helpers as h
from .session import main_doc_session, main_orm_session
from .session import project_doc_session, project_orm_session

from filesystem import File

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
            except: # pragma no cover
                log.exception('Error when firing %r', obj)

class NeighborhoodFile(File):
    class __mongometa__:
        session = main_orm_session

    # Override the metadata schema here
    metadata=FieldProperty(dict(
            neighborhood_id=S.ObjectId,
            filename=str))

class Neighborhood(MappedClass):
    '''Provide a grouping of related projects.

    url_prefix - location of neighborhood (may include scheme and/or host)
    css - block of CSS text to add to all neighborhood pages
    acl - list of user IDs who have rights to perform ops on neighborhood.  Empty
        acl implies that any authenticated user can perform the op
        'read' - access the neighborhood (usually [ User.anonymous()._id ])
        'create' - create projects within the neighborhood (open neighborhoods
            will typically have this empty)
        'moderate' - invite projects into the neighborhood, evict projects from
            the neighborhood
        'admin' - update neighborhood ACLs, acts as a superuser with all
            permissions in neighborhood projects
    '''
    class __mongometa__:
        session = main_orm_session
        name = 'neighborhood'

    _id = FieldProperty(S.ObjectId)
    name = FieldProperty(str)
    url_prefix = FieldProperty(str) # e.g. http://adobe.openforge.com/ or projects/
    shortname_prefix = FieldProperty(str, if_missing='')
    css = FieldProperty(str, if_missing='')
    homepage = FieldProperty(str, if_missing='')
    acl = FieldProperty({
            'read':[S.ObjectId],      # access neighborhood at all
            'create':[S.ObjectId],    # create project in neighborhood
            'moderate':[S.ObjectId],    # invite/evict projects
            'admin':[S.ObjectId],  # update ACLs
            })
    projects = RelationProperty('Project')
    allow_browse = FieldProperty(bool, if_missing=True)

    def url(self):
        url = self.url_prefix
        if url.startswith('//'):
            try:
                return request.scheme + ':' + url
            except TypeError: # pragma no cover
                return 'http:' + url
        else:
            return url

    def register_project(self, shortname, user=None, user_project=False):
        '''Register a new project in the neighborhood.  The given user will
        become the project's superuser.  If no user is specified, c.user is used.
        '''
        assert h.re_path_portion.match(shortname.replace('/', '')), \
            'Invalid project shortname'
        from . import auth
        if user is None: user = c.user
        p = Project.query.get(shortname=shortname)
        if p:
            assert p.neighborhood == self, (
                'Project %s exists in neighborhood %s' % (
                    shortname, p.neighborhood.name))
            return p
        database = 'project:' + shortname.replace('/', ':').replace(' ', '_')
        p = Project(neighborhood_id=self._id,
                    shortname=shortname,
                    name=shortname,
                    short_description='',
                    description=(shortname + '\n'
                                 + '=' * 80 + '\n\n'
                                 + 'You can edit this description in the admin page'),
                    database=database,
                    last_updated = datetime.utcnow(),
                    is_root=True)
        try:
            p.configure_project_database()
            with h.push_config(c, project=p, user=user):
                assert auth.ProjectRole.query.find().count() == 0, \
                    'Project roles already exist'
                # Install default named roles (#78)
                role_owner = auth.ProjectRole(name='Admin')
                role_developer = auth.ProjectRole(name='Developer')
                role_member = auth.ProjectRole(name='Member')
                role_auth = auth.ProjectRole(name='*authenticated')
                role_anon = auth.ProjectRole(name='*anonymous')
                # Setup subroles
                role_owner.roles = [ role_developer._id ]
                role_developer.roles = [ role_member._id ]
                p.acl['create'] = [ role_owner._id ]
                p.acl['read'] = [ role_owner._id, role_developer._id, role_member._id,
                                  role_anon._id ]
                p.acl['update'] = [ role_owner._id ]
                p.acl['delete'] = [ role_owner._id ]
                p.acl['tool'] = [ role_owner._id ]
                p.acl['security'] = [ role_owner._id ]
                pr = user.project_role()
                pr.roles = [ role_owner._id, role_developer._id, role_member._id ]
                # Setup builtin tool applications
                if user_project:
                    p.install_app('profile', 'profile')
                else:
                    p.install_app('home', 'home')
                p.install_app('admin', 'admin')
                p.install_app('search', 'search')
                ThreadLocalORMSession.flush_all()
        except:
            ThreadLocalORMSession.close_all()
            log.exception('Error registering project, attempting to drop %s',
                          database)
            try:
                session(p).impl.bind._conn.drop_database(database)
            except:
                log.exception('Error dropping database %s', database)
                pass
            raise
        g.publish('react', 'forge.project_created')
        return p

    def bind_controller(self, controller):
        from pyforge.controllers.project import NeighborhoodController
        controller_attr = self.url_prefix[1:-1]
        setattr(controller, controller_attr, NeighborhoodController(
                self.name, self.shortname_prefix))

    @property
    def icon(self):
        return NeighborhoodFile.query.find({'metadata.neighborhood_id':self._id}).first()

    @property
    def theme(self):
        return Theme.query.find({'neighborhood_id':self._id}).first()

class Theme(MappedClass):
    class __mongometa__:
        session = main_orm_session
        name = 'theme'

    _id=FieldProperty(S.ObjectId)
    name = FieldProperty(str)
    label = FieldProperty(str)
    neighborhood_id = ForeignIdProperty(Neighborhood)
    color1 = FieldProperty(str)
    color2 = FieldProperty(str)
    color3 = FieldProperty(str)
    color4 = FieldProperty(str)
    color5 = FieldProperty(str)
    color6 = FieldProperty(str)

class ProjectFile(File):    
    class __mongometa__:
        session = main_orm_session

    metadata=FieldProperty(dict(
            project_id=S.ObjectId,
            category=str,
            filename=str))

class ProjectCategory(MappedClass):
    class __mongometa__:
        session = main_orm_session
        name='project_category'

    _id=FieldProperty(S.ObjectId)
    parent_id = FieldProperty(S.ObjectId, if_missing=None)
    name=FieldProperty(str)
    label=FieldProperty(str, if_missing='')
    description=FieldProperty(str, if_missing='')

    @property
    def parent_category(self):
        return self.query.get(_id=self.parent_id)

    @property
    def subcategories(self):
        return self.query.find(dict(parent_id=self._id)).all()

class Project(MappedClass):
    class __mongometa__:
        session = main_orm_session
        name='project'

    # Project schema
    _id=FieldProperty(S.ObjectId)
    parent_id = FieldProperty(S.ObjectId, if_missing=None)
    neighborhood_id = ForeignIdProperty(Neighborhood)
    shortname = FieldProperty(str)
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
            'tool':[S.ObjectId],    # install/delete/configure tools
            'security':[S.ObjectId],  # update ACL, roles
            })
    neighborhood_invitations=FieldProperty([S.ObjectId])
    neighborhood = RelationProperty(Neighborhood)
    app_configs = RelationProperty('AppConfig')
    category_id = FieldProperty(S.ObjectId, if_missing=None)
    deleted = FieldProperty(bool, if_missing=False)
    labels = FieldProperty([str])
    last_updated = FieldProperty(datetime, if_missing=None)

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

    def admin_menu(self):
        return []

    @property
    def script_name(self):
        url = self.url()
        if '//' in url:
            return url.rsplit('//')[-1]
        else:
            return url

    def url(self):
        shortname = self.shortname[len(self.neighborhood.shortname_prefix):]
        url = self.neighborhood.url_prefix + shortname + '/'
        if url.startswith('//'):
            try:
                return request.scheme + ':' + url
            except TypeError: # pragma no cover
                return 'http:' + url
        else:
            return url

    def get_screenshots(self):
        return ProjectFile.query.find({'metadata.project_id':self._id, 'metadata.category':'screenshot'}).all()

    @property
    def icon(self):
        return ProjectFile.query.find({'metadata.project_id':self._id, 'metadata.category':'icon'}).first()

    @property
    def description_html(self):
        return g.markdown.convert(self.description)

    @property
    def parent_project(self):
        if self.is_root: return None
        return self.query.get(_id=self.parent_id)

    @property
    def category(self):
        return ProjectCategory.query.find(dict(_id=self.category_id)).first()

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
        q = self.query.find(dict(shortname={'$gt':self.shortname})).sort('shortname')
        for project in q:
            if project.shortname.startswith(self.shortname + '/'):
                yield project
            else:
                break

    @property
    def direct_subprojects(self):
        return self.query.find(dict(parent_id=self._id))

    @property
    def roles(self):
        from . import auth
        with h.push_config(c, project=self):
            roles = auth.ProjectRole.query.find({'name':{'$in':['Admin','Developer']}}).all()
            roles = roles + auth.ProjectRole.query.find({'name':None,'roles':{'$in':[r._id for r in roles]}}).all()
            return sorted(roles, key=lambda r:r.display())

    @property
    def accolades(self):
        from .artifact import AwardGrant
        return AwardGrant.query.find(dict(granted_to_project_id=self._id)).all()

    def install_app(self, ep_name, mount_point, **override_options):
        assert h.re_path_portion.match(mount_point), 'Invalid mount point'
        assert self.app_instance(mount_point) is None
        for ep in pkg_resources.iter_entry_points('pyforge', ep_name):
            App = ep.load()
            break
        else: 
            # Try case-insensitive install
            for ep in pkg_resources.iter_entry_points('pyforge'):
                if ep.name.lower() == ep_name:
                    App = ep.load()
                    break
            else: # pragma no cover
                raise exc.HTTPNotFound, ep_name
        options = App.default_options()
        options['mount_point'] = mount_point
        options.update(override_options)
        cfg = AppConfig(
            project_id=self._id,
            tool_name=ep.name,
            options=options,
            acl=dict((p,[]) for p in App.permissions))
        app = App(self, cfg)
        with h.push_config(c, project=self, app=app):
            session(cfg).flush()
            app.install(self)
        return app

    def uninstall_app(self, mount_point):
        app = self.app_instance(mount_point)
        if app is None: return
        with h.push_config(c, project=self, app=app):
            app.uninstall(self)

    def app_instance(self, mount_point_or_config):
        if isinstance(mount_point_or_config, AppConfig):
            app_config = mount_point_or_config
        else:
            app_config = self.app_config(mount_point_or_config)
        if app_config is None:
            return None
        App = app_config.load()
        if App is None: # pragma no cover
            return None
        else:
            return App(self, app_config)

    def app_config(self, mount_point):
        return AppConfig.query.find({
                'project_id':self._id,
                'options.mount_point':mount_point}).first()

    def new_subproject(self, name, install_apps=True):
        assert h.re_path_portion.match(name), 'Invalid subproject shortname'
        shortname = self.shortname + '/' + name
        sp = Project(
            parent_id=self._id,
            neighborhood_id=self.neighborhood_id,
            shortname=shortname,
            name=name,
            database=self.database,
            last_updated = datetime.utcnow(),
            is_root=False)
        with h.push_config(c, project=sp):
            AppConfig.query.remove(dict(project_id=c.project._id))
            if install_apps:
                sp.install_app('home', 'home')
                sp.install_app('admin', 'admin')
                sp.install_app('search', 'search')
            g.publish('react', 'forge.project_created')
        return sp

    def delete(self):
        # Cascade to subprojects
        for sp in self.direct_subprojects:
            sp.delete()
        # Cascade to app configs
        for ac in self.app_configs:
            ac.delete()
        MappedClass.delete(self)

    def render_widget(self, widget):
        app = self.app_instance(widget['mount_point'])
        with h.push_config(c, project=self, app=app):
            return getattr(app.widget(app), widget['widget_name'])()

    def breadcrumbs(self):
        entry = ( self.name, self.url() )
        if self.parent_project:
            return self.parent_project.breadcrumbs() + [ entry ]
        else:
            return [ (self.neighborhood.name, self.neighborhood.url())] + [ entry ]

    def users(self):
        def uniq(users):
            t = {}
            for user in users:
                t[user.username] = user
            return t.values()
        project_users = uniq([r.user for r in self.roles if not r.user.username.startswith('*')])
        return project_users

    def user_in_project(self, username=None):
        from .auth import User
        return User.query.find({'_id':{'$in':[role.user_id for role in c.project.roles]},'username':username}).first()

    def configure_project_database(self):
        # Configure flyway migration info
        from flyway.model import MigrationInfo
        from flyway.migrate import Migration
        with h.push_config(c, project=self):
            mi = project_doc_session.get(MigrationInfo)
            if mi is None:
                mi = MigrationInfo.make({})
            mi.versions.update(Migration.latest_versions())
            project_doc_session.save(mi)
            # Configure indexes
            for mc in MappedClass._registry.itervalues():
                if mc.__mongometa__.session == project_orm_session:
                    project_orm_session.ensure_indexes(mc)

class AppConfig(MappedClass):
    class __mongometa__:
        session = project_orm_session
        name='config'

    # AppConfig schema
    _id=FieldProperty(S.ObjectId)
    project_id=ForeignIdProperty(Project)
    discussion_id=ForeignIdProperty('Discussion')
    tool_name=FieldProperty(str)
    version=FieldProperty(str)
    options=FieldProperty(None)
    project = RelationProperty(Project, via='project_id')
    discussion = RelationProperty('Discussion', via='discussion_id')

    # acl[permission] = [ role1, role2, ... ]
    acl = FieldProperty({str:[S.ObjectId]}) 

    def load(self):
        for ep in pkg_resources.iter_entry_points(
            'pyforge', self.tool_name):
            return ep.load()
        return None

    def script_name(self):
        return self.project.script_name + self.options.mount_point + '/'

    def url(self):
        return self.project.url() + self.options.mount_point + '/'

    def breadcrumbs(self):
        return self.project.breadcrumbs() + [
            (self.options.mount_point, self.url()) ]
            
    def grant_permission(self, permission, role=None):
        from . import auth
        if role is None: role = c.user
        if not isinstance(role, auth.ProjectRole):
            role = role.project_role()
        if role._id not in self.acl[permission]:
            self.acl[permission].append(role._id)

    def revoke_permission(self, permission, role=None):
        from . import auth
        if role is None: role = c.user
        if not isinstance(role, auth.ProjectRole):
            role = role.project_role()
        if role._id in self.acl[permission]:
            self.acl[permission].remove(role._id)

