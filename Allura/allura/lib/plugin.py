'''
Allura plugins for authentication and project registration
'''
import re
import os
import logging
import subprocess

from random import randint
from hashlib import sha256
from base64 import b64encode
from datetime import datetime

import ldap
from ldap import modlist
import pkg_resources
from tg import config
from pylons import g, c
from webob import exc

from ming.utils import LazyProperty
from ming.orm import session
from ming.orm import ThreadLocalORMSession

from allura.lib import helpers as h
from allura.lib import exceptions as forge_exc

log = logging.getLogger(__name__)

class AuthenticationProvider(object):

    def __init__(self, request):
        self.request = request

    @classmethod
    def get(cls, request):
        try:
            result = cls._loaded_ep
        except AttributeError:
            method = config.get('auth.method', 'local')
            for ep in pkg_resources.iter_entry_points(
                'allura.auth', method):
                break
            else:
                return None
            result = cls._loaded_ep = ep.load()
        return result(request)

    @LazyProperty
    def session(self):
        return self.request.environ['beaker.session']

    def authenticate_request(self):
        from allura import model as M
        user = M.User.query.get(_id=self.session.get('userid', None))
        if user is None:
            return M.User.anonymous()
        return user

    def register_user(self, user_doc):
        raise NotImplementedError, 'register_user'

    def _login(self):
        raise NotImplementedError, '_login'

    def login(self, user=None):
        try:
            if user is None: user = self._login()
            self.session['userid'] = user._id
            self.session.save()
            return user
        except exc.HTTPUnauthorized:
            self.logout()
            raise

    def logout(self):
        self.session['userid'] = None
        self.session.save()

    def by_username(self, username):
        raise NotImplementedError, 'by_username'

    def set_password(self, user, old_password, new_password):
        raise NotImplementedError, 'set_password'

    def upload_sshkey(self, username, pubkey):
        raise NotImplemented, 'upload_sshkey'

class LocalAuthenticationProvider(AuthenticationProvider):

    def register_user(self, user_doc):
        from allura import model as M
        return M.User(**user_doc)

    def _login(self):
        user = self.by_username(self.request.params['username'])
        if not self._validate_password(user, self.request.params['password']):
            raise exc.HTTPUnauthorized()
        return user

    def _validate_password(self, user, password):
        if user is None: return False
        if not user.password: return False
        salt = str(user.password[6:6+user.SALT_LEN])
        check = self._encode_password(password, salt)
        if check != user.password: return False
        return True

    def by_username(self, username):
        from allura import model as M
        un = re.escape(username)
        un = un.replace(r'\_', '[-_]')
        un = un.replace(r'\-', '[-_]')
        rex = re.compile('^' + un + '$')
        return M.User.query.get(username=rex)

    def set_password(self, user, old_password, new_password):
        user.password = self._encode_password(new_password)

    def _encode_password(self, password, salt=None):
        from allura import model as M
        if salt is None:
            salt = ''.join(chr(randint(1, 0x7f))
                           for i in xrange(M.User.SALT_LEN))
        hashpass = sha256(salt + password.encode('utf-8')).digest()
        return 'sha256' + salt + b64encode(hashpass)

class LdapAuthenticationProvider(AuthenticationProvider):

    def register_user(self, user_doc):
        from allura import model as M
        password = user_doc['password'].encode('utf-8')
        result = M.User(**user_doc)
        dn_u = 'uid=%s,%s' % (user_doc['username'], config['auth.ldap.suffix'])
        uid = str(M.AuthGlobals.get_next_uid())
        try:
            con = ldap.initialize(config['auth.ldap.server'])
            con.bind_s(config['auth.ldap.admin_dn'],
                       config['auth.ldap.admin_password'])
            uname = user_doc['username'].encode('utf-8')
            display_name = user_doc['display_name'].encode('utf-8')
            ldif_u = modlist.addModlist(dict(
                uid=uname,
                userPassword=password,
                objectClass=['account', 'posixAccount' ],
                cn=display_name,
                uidNumber=uid,
                gidNumber='10001',
                homeDirectory='/home/' + uname,
                loginShell='/bin/bash',
                gecos=uname,
                description='SCM user account'))
            try:
                con.add_s(dn_u, ldif_u)
            except ldap.ALREADY_EXISTS:
                log.exception('Trying to create existing user %s', uname)
                raise
            con.unbind_s()
            argv = ('schroot -d / -c %s -u root /ldap-userconfig.py init %s' % (
                config['auth.ldap.schroot_name'], user_doc['username'])).split()
            p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            rc = p.wait()
            if rc != 0:
                log.error('Error creating home directory for %s',
                          user_doc['username'])
        except:
            raise
        return result

    def upload_sshkey(self, username, pubkey):
            argv = ('schroot -d / -c %s -u root /ldap-userconfig.py upload %s' % (
                config['auth.ldap.schroot_name'], username)).split() + [ pubkey ]
            p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            rc = p.wait()
            if rc != 0:
                errmsg = p.stdout.read()
                log.exception('Error uploading public SSH key for %s: %s',
                              username, errmsg)
                assert False, errmsg

    def by_username(self, username):
        from allura import model as M
        return M.User.query.get(username=username)

    def set_password(self, user, old_password, new_password):
        try:
            import pdb; pdb.set_trace()
            dn = 'uid=%s,%s' % (user.username, config['auth.ldap.suffix'])
            con = ldap.initialize(config['auth.ldap.server'])
            con.bind_s(dn, old_password.encode('utf-8'))
            con.modify_s(dn, [(ldap.MOD_REPLACE, 'userPassword', new_password.encode('utf-8'))])
            con.unbind_s()
        except ldap.INVALID_CREDENTIALS:
            raise exc.HTTPUnauthorized()

    def _login(self):
        from allura import model as M
        user = M.User.query.get(username=self.request.params['username'])
        if user is None: raise exc.HTTPUnauthorized()
        try:
            dn = 'uid=%s,%s' % (user.username, config['auth.ldap.suffix'])
            con = ldap.initialize(config['auth.ldap.server'])
            con.bind_s(dn, self.request.params['password'])
            con.unbind_s()
        except ldap.INVALID_CREDENTIALS:
            raise exc.HTTPUnauthorized()
        return user

class ProjectRegistrationProvider(object):

    @classmethod
    def get(cls):
        method = config.get('registration.method', 'local')
        for ep in pkg_resources.iter_entry_points('allura.project_registration', method):
            return ep.load()()

    def register_neighborhood_project(self, neighborhood, users):
        from allura import model as M
        shortname='--init--'
        p = M.Project.query.get(
            neighborhood_id=neighborhood._id,
            shortname=shortname)
        if p: raise forge_exc.ProjectConflict()
        name = 'Home Project for %s' % neighborhood.name
        database_uri = M.Project.default_database_uri(shortname)
        p = M.Project(neighborhood_id=neighborhood._id,
                    shortname=shortname,
                    name=name,
                    short_description='',
                    description=('You can edit this description in the admin page'),
                    homepage_title = '# ' + name,
                    database_uri=database_uri,
                    last_updated = datetime.utcnow(),
                    is_root=True)
        try:
            p.configure_project(
                users=users,
                is_user_project=False,
                apps=[
                    ('wiki', 'home'),
                    ('admin', 'admin')])
        except:
            ThreadLocalORMSession.close_all()
            log.exception('Error registering project %s' % p)
            raise
        return p

    def register_project(self, neighborhood, shortname, user, user_project):
        '''Register a new project in the neighborhood.  The given user will
        become the project's superuser.  If no user is specified, c.user is used.
        '''
        from allura import model as M
        assert h.re_path_portion.match(shortname.replace('/', '')), \
            'Invalid project shortname'
        try:
            p = M.Project.query.get(shortname=shortname)
            if p: raise forge_exc.ProjectConflict()
            p = M.Project(neighborhood_id=neighborhood._id,
                        shortname=shortname,
                        name=shortname,
                        short_description='',
                        description=('You can edit this description in the admin page'),
                        homepage_title=shortname,
                        database_uri=M.Project.default_database_uri(shortname),
                        last_updated = datetime.utcnow(),
                        is_root=True)
            p.configure_project(
                users=[user],
                is_user_project=user_project)
        except forge_exc.ProjectConflict:
            raise
        except:
            ThreadLocalORMSession.close_all()
            log.exception('Error registering project %s' % p)
            raise
        ThreadLocalORMSession.flush_all()
        with h.push_config(c, project=p, user=user):
            # have to add user to context, since this may occur inside auth code for user-project reg, and c.user isn't set yet
            g.publish('react', 'forge.project_created')
        return p

    def register_subproject(self, project, name, user, install_apps):
        from allura import model as M
        assert h.re_path_portion.match(name), 'Invalid subproject shortname'
        shortname = project.shortname + '/' + name
        sp = M.Project(
            parent_id=project._id,
            neighborhood_id=project.neighborhood_id,
            shortname=shortname,
            name=name,
            database_uri=project.database_uri,
            last_updated = datetime.utcnow(),
            is_root=False)
        with h.push_config(c, project=sp):
            M.AppConfig.query.remove(dict(project_id=c.project._id))
            if install_apps:
                sp.install_app('home', 'home')
                sp.install_app('admin', 'admin')
                sp.install_app('search', 'search')
            g.publish('react', 'forge.project_created')
        return sp

    def delete_project(self, project, user):
        for sp in project.subprojects:
            self.delete_project(sp, user)
        project.deleted = True

    def undelete_project(self, project, user):
        project.deleted = False
        for sp in project.subprojects:
            self.undelete_project(sp, user)

    def best_download_url(self, project):
        '''This is the url needed to render a download button.
           It should be overridden for your specific envirnoment'''
        return None

class ThemeProvider(object):
    master_template = 'jinja_master/master.html'
    jinja_macros = 'jinja_master/theme_macros.html'
    nav_menu = 'jinja_master/nav_menu.html'
    top_nav = 'jinja_master/top_nav.html'
    sidebar_menu = 'jinja_master/sidebar_menu.html'
    base_css = ('css/site_style.css', 'allura')
    theme_css = ['css/allura.css']
    icons = {
        'subproject': {
            24: 'images/ext_24.png',
            32: 'images/ext_32.png',
            48: 'images/ext_48.png'
        }
    }

    @LazyProperty
    def password_change_form(self):
        from allura.lib.widgets.forms import PasswordChangeForm
        return PasswordChangeForm(action='/auth/prefs/change_password')

    @LazyProperty
    def upload_key_form(self):
        from allura.lib.widgets.forms import UploadKeyForm
        return UploadKeyForm(action='/auth/prefs/upload_sshkey')

    @property
    def master(self):
        return self.master_template

    @classmethod
    def get(cls):
        name = config.get('theme', 'allura')
        for ep in pkg_resources.iter_entry_points('allura.theme', name):
            log.info("Loading theme '%s'", name)
            return ep.load()()
        log.critical("Could not find theme '%s'", name)

    def app_icon_url(self, app, size):
        """returns the default icon for the given app (or non-app thing like 'subproject').
            Takes an instance of class Application, or else a string.
            Expected to be overriden by derived Themes.
        """
        if isinstance(app, str):
            if app in self.icons and size in self.icons[app]:
                return g.forge_static(self.icons[app][size])
            else:
                for ep in pkg_resources.iter_entry_points('allura', app):
                    app_class = ep.load()
                    return app_class.icon_url(size)
        else:
            return app.icon_url(size)

class LocalProjectRegistrationProvider(ProjectRegistrationProvider):
    pass

class UserPreferencesProvider(object):

    @classmethod
    def get(cls):
        method = config.get('user_prefs_storage.method', 'local')
        for ep in pkg_resources.iter_entry_points('allura.user_prefs', method):
            return ep.load()()

    def get_pref(self, user, pref_name):
        raise NotImplementedError, 'get_pref'

    def save_pref(self, user, pref_name, pref_value):
        raise NotImplementedError, 'set_pref'

    def find_by_display_name(self, name, substring=True):
        raise NotImplementedError, 'find_by_display_name'

class LocalUserPreferencesProvider(UserPreferencesProvider):

    def get_pref(self, user, pref_name):
        if pref_name in user.preferences:
            return user.preferences[pref_name]
        else:
            return getattr(user, pref_name)

    def set_pref(self, user, pref_name, pref_value):
        if pref_name in user.preferences:
            user.preferences[pref_name] = pref_value
        else:
            setattr(user, pref_name, pref_value)

    def find_by_display_name(self, name, substring=True):
        from allura import model as M
        if not substring:
            raise NotImplementedError, 'non-substring'
        name_regex = re.compile('(?i)%s' % re.escape(name))
        users = M.User.query.find(dict(
                display_name=name_regex)).sort('username').all()
        return users
