#-*- python -*-
import logging
import re
import sys
import shutil
from subprocess import Popen

# Non-stdlib imports
import pkg_resources
from tg import expose, validate, redirect, response, config
from tg.decorators import with_trailing_slash, without_trailing_slash
import pylons
from pylons import g, c, request
from formencode import validators
from pymongo import bson
from webob import exc

from ming.orm.base import mapper
from pymongo.bson import ObjectId

# Pyforge-specific imports
from pyforge.app import Application, ConfigOption, SitemapEntry
from pyforge.lib.helpers import push_config, DateTimeConverter, mixin_reactors
from pyforge.lib.search import search
from pyforge.lib.decorators import audit, react
from pyforge.lib.security import require, has_artifact_access
from pyforge.model import ProjectRole, User, ArtifactReference, Feed

# Local imports
from forgesvn import model
from forgesvn import version
from .reactors import reactors

log = logging.getLogger(__name__)


class ForgeSVNApp(Application):
    '''This is the SVN app for PyForge'''
    __version__ = version.__version__
    permissions = [ 'read', 'write', 'create', 'admin' ]

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()

    @property
    def sitemap(self):
        menu_id = self.config.options.mount_point.title()
        with push_config(c, app=self):
            return [
                SitemapEntry(menu_id, '.')[self.sidebar_menu()] ]

    def sidebar_menu(self):
        links = [ SitemapEntry('Home',c.app.url, ui_icon='home') ]
        return links

    @property
    def repo(self):
        return model.SVNRepository.query.get(app_config_id=self.config._id)

    @property
    def templates(self):
         return pkg_resources.resource_filename('forgesvn', 'templates')

    def install(self, project):
        'Set up any default permissions and roles here'
        self.config.options['project_name'] = project._id
        super(ForgeSVNApp, self).install(project)
        # Setup permissions
        role_developer = ProjectRole.query.get(name='Developer')._id
        role_auth = ProjectRole.query.get(name='*authenticated')._id
        self.config.acl.update(
            read=c.project.acl['read'],
            create=[role_developer],
            write=[role_developer],
            admin=c.project.acl['plugin'])


    def uninstall(self, project):
        g.publish('audit', 'scm.svn.uninstall', dict(project_id=project._id))

    @audit('scm.svn.uninstall')
    def _uninstall(self, routing_key, data):
        "Remove all the plugin's artifacts and the physical repository"
        repo = self.repo
        if repo is not None and repo.path:
            shutil.rmtree(repo.path, ignore_errors=True)
        model.SVNRepository.query.remove(dict(app_config_id=self.config._id))
        super(ForgeSVNApp, self).uninstall(project_id=data['project_id'])

class RootController(object):

    def __init__(self):
        setattr(self, 'feed.atom', self.feed)
        setattr(self, 'feed.rss', self.feed)

    @expose('forgesvn.templates.index')
    def index(self):
        host = config.get('scm.host', request.host)
        return dict(repo=c.app.repo, host=host)

    @expose()
    def init(self, name=None):
        require(has_artifact_access('create'))
        if request.method != 'POST':
            raise Exception('init must be a POST request')
        repo = c.app.repo
        if repo is None:
            repo = model.SVNRepository()
        if not name:
            name = c.project.shortname.split('/')[-1]
        path = '/svn/' + c.project.shortname + '/' + c.app.config.options.mount_point + '/'
        repo.name = name
        repo.path = path
        repo.tool = 'svn'
        repo.status = 'creating'
        g.publish('audit', 'scm.svn.init', dict(repo_name=name, repo_path=path))
        redirect('.')

    #Instantiate a Page object, and continue dispatch there
#    @expose()
#    def _lookup(self, pname, *remainder):
#        return PageController(pname), remainder

    @with_trailing_slash
    @expose('forgewiki.templates.search')
    @validate(dict(q=validators.UnicodeString(if_empty=None),
                   history=validators.StringBool(if_empty=False)))
    def search(self, q=None, history=None):
        'local wiki search'
        results = []
        count=0
        if not q:
            q = ''
        else:
            search_query = '''%s
            AND is_history_b:%s
            AND project_id_s:%s
            AND mount_point_s:%s''' % (
                q, history, c.project._id, c.app.config.options.mount_point)
            results = search(search_query)
            if results: count=results.hits
        return dict(q=q, history=history, results=results or [], count=count)

    @without_trailing_slash
    @expose()
    @validate(dict(
            since=DateTimeConverter(if_empty=None),
            until=DateTimeConverter(if_empty=None),
            offset=validators.Int(if_empty=None),
            limit=validators.Int(if_empty=None)))
    def feed(self, since=None, until=None, offset=None, limit=None):
        if request.environ['PATH_INFO'].endswith('.atom'):
            feed_type = 'atom'
        else:
            feed_type = 'rss'
        title = 'Recent changes to %s' % c.app.config.options.mount_point
        feed = Feed.feed(
            {'artifact_reference.mount_point':c.app.config.options.mount_point,
             'artifact_reference.project_id':c.project._id},
            feed_type,
            title,
            c.app.url,
            title,
            since, until, offset, limit)
        response.headers['Content-Type'] = ''
        response.content_type = 'application/xml'
        return feed.writeString('utf-8')

mixin_reactors(ForgeSVNApp, reactors)
