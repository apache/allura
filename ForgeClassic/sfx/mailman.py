#-*- python -*-
import logging

from tg import expose, redirect, validate, flash
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import c

from allura.app import DefaultAdminController
from allura.lib import helpers as h

from . import widgets
from . import model as SM
from .app_base import SFXBaseApp

log = logging.getLogger(__name__)

class W:
    admin_list = widgets.ListAdmin()
    new_list = widgets.NewList()
    search = widgets.SubscriberSearch()
    password_change = widgets.PasswordChange()

class MailmanApp(SFXBaseApp):
    '''This is the Mailing List app for PyForge'''
    tool_label='Mailing List'
    default_mount_label='List'
    default_mount_point='sfx-list'
    ordinal=8

    class AdminController(DefaultAdminController):

        @with_trailing_slash
        @expose('sfx.templates.mailman_admin')
        def index(self, **kw):
            c.list = W.admin_list
            c.new = W.new_list
            return dict(lists=list(SM.List.find()))

        @without_trailing_slash
        @expose()
        @validate(form=W.new_list)
        def create(self, name=None, **kw):
            SM.List.create(name=c.project.shortname + '-' + name,
                           **kw)
            redirect('.')

        @without_trailing_slash
        @expose()
        @h.vardec
        @validate(form=W.admin_list)
        def save(self, lists=None, **kw):
            if lists is None: redirect('.')
            with h.twophase_transaction(
                SM.site_meta.bind, SM.epic_meta.bind, SM.mail_meta.bind):
                for args in lists:
                    lst = SM.List(args['name'])
                    lst.update(
                        description = args['description'],
                        is_public = args['is_public'])
                    if args['is_public'] == SM.List.DELETE:
                        lst.delete()
            redirect('.')

        @expose()
        def _lookup(self, name, *remainder):
            return ListAdmin(SM.List(name)), remainder

class ListAdmin(object):

    def __init__(self, mailing_list):
        self._list = mailing_list
        self.subscribers = ListSubscribers(mailing_list)
        self.admin_password = AdminPassword(mailing_list)

class ListSubscribers(object):

    def __init__(self, mailing_list):
        self._list = mailing_list

    @with_trailing_slash
    @expose('sfx.templates.mailman_subscriber_query')
    def index(self, **kw):
        c.search = W.search
        return dict(ml=self._list)

    @without_trailing_slash
    @expose('sfx.templates.mailman_subscriber_display')
    @validate(W.search)
    def display(self, search_criteria=None, sort_by=None):
        subscribers = list(self._list.subscribers(search_criteria, sort_by))
        sort_by = sort_by or 'user name'
        return dict(
            ml=self._list,
            search=search_criteria,
            subscribers=subscribers,
            sort_by=sort_by)

class AdminPassword(object):

    def __init__(self, mailing_list):
        self._list = mailing_list

    @with_trailing_slash
    @expose('sfx.templates.mailman_admin_password')
    def index(self, **kw):
        c.form = W.password_change
        return dict(ml=self._list)

    @expose()
    @validate(W.password_change, error_handler=index)
    def save(self, new_password=None, confirm_password=None):
        self._list.change_password(new_password)
        flash('Submitted password change request for list %s.'
              '  Please allow a few minutes for this to take effect.'
              % self._list.name)
        redirect('.')
