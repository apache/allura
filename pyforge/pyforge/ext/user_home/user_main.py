import difflib
import logging
from pprint import pformat

import pkg_resources
from pylons import c, request
from tg import expose, redirect, flash
from webob import exc
from pymongo.bson import ObjectId


from pyforge import version
from pyforge.app import Application, WidgetController, ConfigOption, SitemapEntry
from pyforge.lib.helpers import push_config, html, vardec
from pyforge.lib.dispatch import _dispatch
from pyforge.ext.project_home import model as M
from pyforge.lib.security import require, has_project_access
from pyforge.model import nonce

log = logging.getLogger(__name__)

class UserWidgets(WidgetController):
    widgets=['welcome']

    def __init__(self, app): pass

    def welcome(self):
        return self.portlet('<h1>Please configure your widgets </h1>')

class UserHomeApp(Application):
    __version__ = version.__version__
    widget = UserWidgets
    installable = False

    def __init__(self, user, config):
        Application.__init__(self, user, config)
        self.root = UserHomeController()
        self.templates = pkg_resources.resource_filename(
            'pyforge.ext.user_home', 'templates')

    @property
    def sitemap(self):
        menu_id = 'User'
        return []

    def sidebar_menu(self):
        return [ SitemapEntry('Configure', 'configuration')]

    # @property
    # def templates(self):
    #     return

    def install(self, project):
        pr = c.user.project_role()
        if pr:
            for perm in self.permissions:
                self.config.acl[perm] = [ pr._id ]

    def uninstall(self, project): # pragma no cover
        raise NotImplementedError, "uninstall"

class UserHomeController(object):

    def _check_security(self):
        require(has_project_access('read'),
                'Read access required')

    @expose('pyforge.ext.user_home.templates.user_index')
    def index(self):
        config = M.PortalConfig.current()
        return dict(
            layout_class=config.layout_class,
            layout=config.rendered_layout())

    @expose('pyforge.ext.user_home.templates.user_dashboard_configuration')
    def configuration(self):
        config = M.PortalConfig.current()
        mount_points = [
            (ac.options.mount_point, ac.load())
            for ac in c.project.app_configs ]
        widget_types = [
            dict(mount_point=mp, widget_name=w)
            for mp, app_class in mount_points
            for w in app_class.widget.widgets ]
        return dict(
            layout_class=config.layout_class,
            layout=config.layout,
            widget_types=widget_types)

    @vardec
    @expose()
    def update_configuration(self, divs=None, layout_class=None, new_div=None, **kw):
        config = M.PortalConfig.current()
        config.layout_class = layout_class
        # Handle updated and deleted divs
        if divs is None: divs = []
        new_divs = []
        for div in divs:
            log.info('Got div update:%s', pformat(div))
            if div.get('del'): continue
            new_divs.append(div)
        # Handle new divs
        if new_div:
            new_divs.append(dict(name=nonce(), content=[]))
        config.layout = []
        for div in new_divs:
            content = []
            for w in div.get('content', []):
                if w.get('del'): continue
                mp,wn = w['widget'].split('/')
                content.append(dict(mount_point=mp, widget_name=wn))
            if div.get('new_widget'):
                content.append(dict(mount_point='home', widget_name='welcome'))
            config.layout.append(dict(
                    name=div['name'],
                    content=content))
        redirect('configuration')
