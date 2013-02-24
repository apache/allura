#-*- python -*-
import logging
from pylons import c
import formencode
from formencode import validators
from webob import exc

from allura.app import Application, SitemapEntry
from allura.lib import helpers as h
from allura.lib.security import has_access
from allura import model as M

from forgeorganization import version
from forgeorganization.tool.controller import OrganizationToolController

from ming.orm import session

log = logging.getLogger(__name__)

class ForgeOrganizationToolApp(Application):
    __version__ = version.__version__
    tool_label='Organizations'
    default_mount_label='Organizations'
    default_mount_point='organizations'
    permissions = ['configure', 'read', 'write',
                    'unmoderated_post', 'post', 'moderate', 'admin']
    ordinal=15
    installable=True
    config_options = Application.config_options
    default_external_feeds = []
    icons={
        24:'images/org_24.png',
        32:'images/org_32.png',
        48:'images/org_48.png'
    }
    root = OrganizationToolController()

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        role_admin = M.ProjectRole.by_name('Admin')._id
        role_anon = M.ProjectRole.by_name('*anonymous')._id
        self.config.acl = [
            M.ACE.allow(role_anon, 'read'),
            M.ACE.allow(role_admin, 'admin')]

    def main_menu(self):
        return [SitemapEntry(self.config.options.mount_label.title(), '.')]

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        menu_id = self.config.options.mount_label.title()
        with h.push_config(c, app=self):
            return [
                SitemapEntry(menu_id, '.')[self.sidebar_menu()] ]

    @property
    def show_discussion(self):
        if 'show_discussion' in self.config.options:
            return self.config.options['show_discussion']
        else:
            return True

    @h.exceptionless([], log)
    def sidebar_menu(self):
        base = c.app.url
        links = [SitemapEntry('Home', base)]
        return links

    def admin_menu(self):
        admin_url=c.project.url()+'admin/'+self.config.options.mount_point+'/'
        links = [SitemapEntry(
                     'Involved organizations',
                     admin_url + 'edit_label', 
                     className='admin_modal')]
        return links

    def install(self, project):
        #It doesn't make any sense to install the tool twice on the same 
        #project therefore, if it already exists, it doesn't install it
        #a second time.
        for tool in project.app_configs:
            if tool.tool_name == 'organizationstool':
                if self.config.options.mount_point!=tool.options.mount_point:
                    project.uninstall_app(self.config.options.mount_point)
                    return

    def uninstall(self, project):
        self.config.delete()
        session(self.config).flush()

