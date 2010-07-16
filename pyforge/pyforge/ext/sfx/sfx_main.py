import logging
from contextlib import contextmanager
from datetime import datetime, timedelta

import pylons
from tg import config
from tg.decorators import with_trailing_slash
from formencode import validators as V

from pyforge import version
from pyforge.app import Application
from pyforge.lib.decorators import react
from pyforge.lib import search
from pyforge.lib import helpers as h
from pyforge.lib import plugin
from pyforge import model as M

from .lib.sfx_api import SFXProjectApi, SFXUserApi
from .lib import exceptions as sfx_exc

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
        if config['registration.method'] != 'sfx': return
        api = SFXProjectApi()
        api.update(pylons.c.user, pylons.c.project)

    @classmethod
    @react('forge.project_updated')
    def project_updated(cls, routing_key, doc):
        if config['registration.method'] != 'sfx': return
        api = SFXProjectApi()
        api.update(pylons.c.user, pylons.c.project)

    @classmethod
    @react('forge.project_deleted')
    def project_deleted(cls, routing_key, doc):
        if config['registration.method'] != 'sfx': return
        api = SFXProjectApi()
        api.delete(pylons.c.user, pylons.c.project)

    def sidebar_menu(self):
        return [ ]

    def admin_menu(self):
        return []

    def install(self, project):
        pass # pragma no cover

    def uninstall(self, project):
        pass # pragma no cover

class SFXAuthenticationProvider(plugin.AuthenticationProvider):

    def __init__(self, request):
        super(SFXAuthenticationProvider, self).__init__(request)
        try:
            self.sfx_session_manager = request.environ['allura.sfx_session_manager']
        except TypeError:
            from sf.phpsession import SFXSessionMgr
            self.sfx_session_manager = SFXSessionMgr()
        self.local_ap = plugin.LocalAuthenticationProvider(request)

    def register_user(self, user_doc):
        log.warning("We don't provide user registration; that's SFX's job."
                    "  Delegating to a LocalAuthenticationProvider...")
        return self.local_ap.register_user(user_doc)

    def set_password(self, user, old_password, new_password):
        log.warning("We don't provide password services; that's SFX's job."
                    "  Delegating to a LocalAuthenticationProvider...")
        return self.local_ap.set_password(user, old_password, new_password)

    def authenticate_request(self):
        cookie_name = self.sfx_session_manager.cookie_name
        mgr = self.sfx_session_manager
        if 'userid' in self.session:
            user = super(SFXAuthenticationProvider, self).authenticate_request()
            if user != M.User.anonymous():
                if cookie_name not in self.request.cookies:
                    self.logout()
                    return M.User.anonymous()
                elif self.request.cookies[cookie_name] == self.session.get('sfx-sessid'):
                    return user
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

    def logout(self):
        self.session['sfx-sessid'] = None
        try:
            from pylons import response
            response.delete_cookie(self.sfx_session_manager.cookie_name)
        except:
            pass
        super(SFXAuthenticationProvider, self).logout()

    def _login(self):
        raise TypeError, "We don't provide user login; that's SFX's job"

    def by_username(self, username, extra=None):
        api = SFXUserApi()
        try:
            return api.upsert_user(username, extra)
        except:
            with fake_pylons_context(self.request):
                return api.upsert_user(username, extra)

class SFXProjectRegistrationProvider(plugin.ProjectRegistrationProvider):

    def __init__(self):
        self.api = SFXProjectApi()

    def register_project(self, neighborhood, shortname, user, user_project):
        # Reserve project name with SFX
        try:
            ug_name = self.api.create(user, neighborhood, shortname)
            log.info('SFX Project creation returned: %s', ug_name)
        except sfx_exc.SFXAPIError, exc:
            if user_project: 
                log.exception('SFX project creation error: %r', exc)
                ug_name = None
                return None
            else:
                raise
        p = super(SFXProjectRegistrationProvider, self).register_project(
            neighborhood, shortname, user, user_project)
        p.set_tool_data('sfx', unix_group_name=ug_name)
        self.api.read(p)
        return p

    def register_subproject(self, project, name, user, install_apps):
        if not project.is_root:
            raise sfx_exc.SFXIllegalProject, (
                'Subprojects more than one level deep not supported')
        ug_name = self.api.create(user, project.neighborhood, project.shortname + '/' + name)
        log.info('SFX Subproject creation returned: %s', ug_name)
        p = super(SFXProjectRegistrationProvider, self).register_subproject(
            project, name, user, install_apps)
        p.set_tool_data('sfx', unix_group_name=ug_name)
        self.api.read(p)
        return p

    def delete_project(self, project, user):
        r = self.api.delete(user, project)
        super(SFXProjectRegistrationProvider, self).delete_project(project, user)
        return r

    def undelete_project(self, project, user):
        raise NotImplementedError, 'SFX undelete_project'

    def best_download_url(self, project):
        shortname = project.shortname[len(project.neighborhood.shortname_prefix):]
        short_split = shortname.split('/')
        short_split.reverse()
        short_split = '.'.join(short_split)
        neighborhood_prefix = project.neighborhood.url_prefix.replace('/','')
        proj_name = short_split + (neighborhood_prefix != 'p' and '.' + neighborhood_prefix or '')
        return '/projects/%s/best_release.html' % proj_name

@contextmanager
def fake_pylons_context(request):
    from pyforge.lib.app_globals import Globals
    from pyforge.lib.custom_middleware import MagicalC, environ
    class EmptyClass(object): pass
    pylons.c._push_object(MagicalC(EmptyClass(), environ))
    pylons.g._push_object(Globals())
    pylons.request._push_object(request)
    try:
        yield
    finally:
        pylons.c._pop_object()
        pylons.g._pop_object()
        pylons.request._pop_object()

