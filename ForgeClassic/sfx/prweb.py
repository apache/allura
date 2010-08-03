#-*- python -*-
import logging

from tg import expose, redirect, validate, flash
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import c

from pyforge.app import DefaultAdminController

from . import widgets
from . import model as SM
from .app_base import SFXBaseApp

log = logging.getLogger(__name__)

class W:
    new_vhost = widgets.NewVHost()
    mysql_password = widgets.MySQLPassword()

class VHostApp(SFXBaseApp):
    '''This is the VHOST app for PyForge'''
    tool_label='VHOST'
    default_mount_label='VHOST'
    default_mount_point='sfx-vhost'
    ordinal=8

    class AdminController(DefaultAdminController):

        @with_trailing_slash
        @expose('sfx.templates.vhost_admin')
        def index(self, **kw):
            c.new = W.new_vhost
            return dict(vhosts=list(SM.VHost.find()))

        @expose()
        def create(self, vhostid=None):
            SM.VHost.create(vhostid)
            flash('Virtual host scheduled for creation.')
            redirect('.')

        @expose()
        def delete(self, vhostid=None):
            vhost = SM.VHost.get(vhostid)
            if vhost is None:
                flash('Virtual host %s not found' % vhostid, 'error')
            vhost.delete()
            flash('Virtual host %s deleted' % vhostid)
            redirect('.')

class MySQLApp(SFXBaseApp):
    '''This is the MySQL app for PyForge'''
    tool_label='MySQL Databases'
    default_mount_label='MySQL'
    default_mount_point='sfx-mysql'
    ordinal=9

    class AdminController(DefaultAdminController):

        @with_trailing_slash
        @expose('sfx.templates.mysql_admin')
        def index(self, **kw):
            c.form = W.mysql_password
            return dict(value=SM.MySQL())

        @without_trailing_slash
        @validate(W.mysql_password, error_handler=index)
        @expose()
        def save(self, **kw):
            db = SM.MySQL()
            if hasattr(db, 'passwd_rouser'):
                db.update(**kw)
            else:
                SM.MySQL.create(**kw)
            redirect('.')
