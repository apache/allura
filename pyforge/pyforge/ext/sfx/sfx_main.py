import logging
from contextlib import contextmanager
from datetime import datetime, timedelta

import pylons
from tg.decorators import with_trailing_slash
from formencode import validators as V

from pyforge import version
from pyforge.app import Application
from pyforge.lib.decorators import react
from pyforge.lib import search
from pyforge import model as M

from .lib.sfx_api import SFXProjectApi, SFXUserApi

log = logging.getLogger(__name__)

class SFXApp(Application):
    '''Handles reflecting project changes over to SFX'''
    __version__ = version.__version__
    installable = False
    sitemap=[]
    root=None
    templates=None

    @classmethod
    @react('forge.project_created')
    def project_created(cls, routing_key, doc):
        api = SFXProjectApi()
        api.create(pylons.c.project)

    @classmethod
    @react('forge.project_updated')
    def project_updated(cls, routing_key, doc):
        api = SFXProjectApi()
        api.update(pylons.c.project)

    @classmethod
    @react('forge.project_deleted')
    def project_deleted(cls, routing_key, doc):
        api = SFXProjectApi()
        api.delete(pylons.c.project)

    def sidebar_menu(self):
        return [ ]

    def admin_menu(self):
        return []

    def install(self, project):
        pass # pragma no cover

    def uninstall(self, project):
        pass # pragma no cover

class SFXAuthenticationProvider(M.AuthenticationProvider):

    def __init__(self, request):
        super(SFXAuthenticationProvider, self).__init__(request)
        self.sfx_session_manager = self.session['allura.sfx_session_manager']

    def register_user(self, user_doc):
        raise TypeError, "We don't provide user registration; that's SFX's job"

    def authenticate_request(self):
        cookie_name = self.sfx_session_mgr.cookie_name
        mgr = self.sfx_session_mgr
        if 'userid' in self.session:
            if cookie_name not in self.request.cookies:
                self.logout()
                return M.User.anonymous()
            elif self.request.cookies[cookie_name] == self.session.get('sfx-sessid'):
                # already logged in
                return super(M.AuthPlugin, self).authenticate_request()
        sfx_user_id = mgr.userid_from_session_cookie(self.request.cookies)
        if sfx_user_id:
            server_name = self.request.environ['HTTP_HOST']
            user_data = mgr.user_data(server_name, sfx_user_id)
            user = self.by_username(user_data['username'], user_data)
            self.session['sfx-sessid'] = self.request.cookies[cookie_name]
            self.session['userid'] = user._id
            self.session.save()
            return user
        else:
            return M.User.anonymous()

    def _login(self):
        raise TypeError, "We don't provide user login; that's SFX's job"

    def by_username(self, username):
        api = SFXUserApi()
        with fake_pylons_context(self.request):
            return api.upsert_user(username)


@contextmanager
def fake_pylons_context(request):
    from pyforge.lib.app_globals import Globals
    from pyforge.lib.custom_middleware import MagicalC, environ
    class EmptyClass(object): pass
    pylons.c._push_object(MagicalC(EmptyClass(), environ))
    pylons.g._push_object(Globals())
    pylons.request._push_object(request)
    yield
    pylons.c._pop_object()
    pylons.g._pop_object()
    pylons.request._pop_object()

