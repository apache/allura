#-*- python -*-
import logging

from tg import expose, redirect, flash
from tg.decorators import with_trailing_slash
from pylons import c

from allura.app import DefaultAdminController, SitemapEntry
from allura.lib import helpers as h

from . import model as SM
from .app_base import SFXBaseApp

log = logging.getLogger(__name__)

class HostedAppsApp(SFXBaseApp):
    '''This is the Hosted Apps app for PyForge'''
    permissions = [ 'configure', 'admin', 'read']
    tool_label='Classic Hosted Apps'
    default_mount_label='Hosted Apps'
    default_mount_point='sfx-hosted-apps'
    ordinal=10

    class AdminController(DefaultAdminController):

        @with_trailing_slash
        @expose('sfx.templates.hosted_admin')
        def index(self, **kw):
            all_apps = SM.HostedApp.all()
            enabled_features = set(SM.HostedApp.enabled_features())
            enabled_apps = [ app for app in all_apps if app.feature_type in enabled_features ]
            disabled_apps = [
                app for app in all_apps if app.feature_type not in enabled_features ]
            return dict(
                enabled_apps=enabled_apps,
                disabled_apps=disabled_apps)

        @expose()
        def enable(self, ft=None):
            enabled_features = set(SM.HostedApp.enabled_features())
            if ft in enabled_features: return
            ha = SM.HostedApp.get(ft)
            if ha is None:
                flash('%s not found' % ft, 'error')
            else:
                ha.enable()
                flash('%s queued for enable' % ha.description)
            redirect('.')

        @expose()
        def disable(self, ft=None):
            enabled_features = set(SM.HostedApp.enabled_features())
            if ft not in enabled_features: return
            ha = SM.HostedApp.get(ft)
            if ha is None:
                flash('%s not found' % ft, 'error')
            else:
                ha.disable()
                flash('%s queued for disable' % ha.description)
            redirect('.')

        @expose()
        def grant_admin(self, ft=None):
            enabled_features = set(SM.HostedApp.enabled_features())
            if ft not in enabled_features: return
            ha = SM.HostedApp.get(ft)
            if ha is None:
                flash('%s not found' % ft, 'error')
            else:
                ha.addperm()
                flash('Manage permissions on %s queued for %s' % (
                        ha.description, c.user.username))
            redirect('.')

    def __init__(self, project, config):
        SFXBaseApp.__init__(self, project, config)
        self.root = HostedAppsController()

    def sidebar_menu(self):
        enabled_features = set(SM.HostedApp.enabled_features())
        return [
            SitemapEntry(ha.description, ha.format_column('application_url'))
            for ha in SM.HostedApp.all() if ha.feature_type in enabled_features ]

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        menu_id = self.config.options.mount_label.title()
        return [
            SitemapEntry(menu_id, '.') ]

class HostedAppsController(object):

    @with_trailing_slash
    @expose('sfx.templates.hosted_index')
    def index(self, **kw):
        all_apps = SM.HostedApp.all()
        enabled_features = set(SM.HostedApp.enabled_features())
        enabled_apps = [ app for app in all_apps if app.feature_type in enabled_features ]
        disabled_apps = [ app for app in all_apps if app.feature_type not in enabled_features ]
        return dict(
            enabled_apps=enabled_apps,
            disabled_apps=disabled_apps)
