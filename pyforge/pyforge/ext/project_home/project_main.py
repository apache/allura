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
from pyforge.lib import helpers as h
from pyforge.ext.project_home import model as M
from pyforge import model
from pyforge.lib.security import require, has_project_access

log = logging.getLogger(__name__)

class ProjectWidgets(WidgetController):
    widgets=['welcome']

    def __init__(self, app): pass

    def welcome(self):
        return self.portlet('<p><!-- Please configure your widgets --></p>')

class ProjectHomeApp(Application):
    __version__ = version.__version__
    widget = ProjectWidgets
    installable = False

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = ProjectHomeController()
        self.templates = pkg_resources.resource_filename(
            'pyforge.ext.project_home', 'templates')

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        menu_id = 'Home'
        return [
            SitemapEntry('Home', '.') ]

    @h.exceptionless([], log)
    def sidebar_menu(self):
        return [ SitemapEntry('Configure', 'configuration')]

    def admin_menu(self):
        return []

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

class ProjectHomeController(object):

    def _check_security(self):
        require(has_project_access('read'),
                'Read access required')

    @expose('pyforge.ext.project_home.templates.project_index')
    def index(self):
        config = M.PortalConfig.current()
        return dict(
            layout_class=config.layout_class,
            layout=config.rendered_layout())

    @expose('pyforge.ext.project_home.templates.project_dashboard_configuration')
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

    @h.vardec
    @expose()
    def update_configuration(self, divs=None, layout_class=None, new_div=None, **kw):
        require(has_project_access('update'), 'Update access required')
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
            new_divs.append(dict(name=h.nonce(), content=[]))
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
    
