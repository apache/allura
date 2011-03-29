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
from tg import g, c, session
from webob import exc

from ming.utils import LazyProperty
from ming.orm import state, session
from ming.orm import ThreadLocalORMSession

from allura.lib import helpers as h
from allura.lib import security
from allura.lib import exceptions as forge_exc

log = logging.getLogger(__name__)

class AuthenticationProvider(object):
    '''
    An interface to provide authentication services for Allura.

    To use a new provider, expose an entry point in setup.py:

        [allura.auth]
        myprovider = foo.bar:MyAuthProvider

    Then in your .ini file, set auth.method=myprovider
    '''

    def __init__(self, request):
        self.request = request

    @classmethod
    def get(cls, request):
        '''returns the AuthenticationProvider instance for this request'''
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

    def authenticate_request(self):
        from allura import model as M
        user = M.User.query.get(_id=session.get('userid', None))
        if user is None:
            return M.User.anonymous()
        return user

    def register_user(self, user_doc):
        '''
        Register a user.

        :param user_doc: a dict with 'username' and 'display_name'.  Optionally 'password' and others
        :rtype: :class:`User <allura.model.auth.User>`
        '''
        raise NotImplementedError, 'register_user'

    def _login(self):
        '''
        Authorize a user, usually using self.request.params['username'] and ['password']

        :rtype: :class:`User <allura.model.auth.User>`
        :raises: HTTPUnauthorized if user not found, or credentials are not valid
        '''
        raise NotImplementedError, '_login'

    def login(self, user=None):
        try:
            if user is None: user = self._login()
            session['userid'] = user._id
            return user
        except exc.HTTPUnauthorized:
            self.logout()
            raise

    def logout(self):
        self.session['userid'] = None
        self.session.save()

    def by_username(self, username):
        '''
        Find a user by username.

        :rtype: :class:`User <allura.model.auth.User>` or None
        '''
        raise NotImplementedError, 'by_username'

    def set_password(self, user, old_password, new_password):
        '''
        Set a user's password.

        :param user: a :class:`User <allura.model.auth.User>`
        :rtype: None
        :raises: HTTPUnauthorized if old_password is not valid
        '''
        raise NotImplementedError, 'set_password'

    def upload_sshkey(self, username, pubkey):
        '''
        Upload an SSH Key.  Providers do not necessarily need to implement this.

        :rtype: None
        :raises: AssertionError with user message, upon any error
        '''
        raise NotImplemented, 'upload_sshkey'

class LocalAuthenticationProvider(AuthenticationProvider):
    '''
    Stores user passwords on the User model, in mongo.  Uses per-user salt and
    SHA-256 encryption.
    '''

    def register_user(self, user_doc):
        from allura import model as M
        u = M.User(**user_doc)
        if 'password' in user_doc:
            u.set_password(user_doc['password'])
        return u

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
    '''
    Project registration services for Allura.  This is a full implementation
    and the default.  Extend this class with your own if you need to add more
    functionality.

    To use a new provider, expose an entry point in setup.py:

        [allura.project_registration]
        myprovider = foo.bar:MyAuthProvider

    Then in your .ini file, set registration.method=myprovider
    '''

    @classmethod
    def get(cls):
        method = config.get('registration.method', 'local')
        for ep in pkg_resources.iter_entry_points('allura.project_registration', method):
            return ep.load()()

    def name_taken(self, project_name):
        from allura import model as M
        p = M.Project.query.get(shortname=project_name)
        if p:
            return 'This project name is taken.'
        for check in self.extra_name_checks():
            if re.match(str(check[1]),project_name) is not None:
                return check[0]
        return False

    def extra_name_checks(self):
        '''This should be a list or iterator containing tuples.
        The first tiem in the tuple should be an error message and the
        second should be a regex. If the user attempts to register a
        project with a name that matches the regex, the field will
        be marked invalid with the message displayed to the user.
        '''
        return []

    def register_neighborhood_project(self, neighborhood, users, allow_register=False):
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
        if allow_register:
            role_auth = M.ProjectRole.authenticated(p)
            security.simple_grant(p.acl, role_auth._id, 'register')
            state(p).soil()
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
            # have to add user to context, since this may occur inside auth code
            # for user-project reg, and c.user isn't set yet
            g.post_event('project_created')
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
            g.post_event('project_created')
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
    '''
    Theme information for Allura.  This is a full implementation
    and the default.  Extend this class with your own if you need to add more
    functionality.

    To use a new provider, expose an entry point in setup.py:

        [allura.theme]
        myprovider = foo.bar:MyThemeProvider

    Then in your .ini file, set theme=mytheme

    The variables referencing jinja template files can be changed to point at your
    own jinja templates.  Use the standard templates as a reference, you should
    provide matching macros and block names.

    :var base_css: tuple of (css-resource, theme-name), or just a string css-resource
    :var icons: a dictionary of sized icons for each tool
    '''

    master_template = 'allura:templates/jinja_master/master.html'
    jinja_macros = 'allura:templates/jinja_master/theme_macros.html'
    nav_menu = 'allura:templates/jinja_master/nav_menu.html'
    top_nav = 'allura:templates/jinja_master/top_nav.html'
    sidebar_menu = 'allura:templates/jinja_master/sidebar_menu.html'
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
        '''
        :return: None, or an easywidgets Form to render on the user preferences page
        '''
        from allura.lib.widgets.forms import PasswordChangeForm
        return PasswordChangeForm(action='/auth/prefs/change_password')

    @LazyProperty
    def upload_key_form(self):
        '''
        :return: None, or an easywidgets Form to render on the user preferences page
        '''
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
    '''
    An interface for user preferences, like display_name and email_address

    To use a new provider, expose an entry point in setup.py:

        [allura.user_prefs]
        myprefs = foo.bar:MyUserPrefProvider

    Then in your .ini file, set user_prefs_storage.method=myprefs
    '''

    @classmethod
    def get(cls):
        method = config.get('user_prefs_storage.method', 'local')
        for ep in pkg_resources.iter_entry_points('allura.user_prefs', method):
            return ep.load()()

    def get_pref(self, user, pref_name):
        '''
        :param user: a :class:`User <allura.model.auth.User>`
        :param str pref_name:
        :return: pref_value
        :raises: AttributeError if pref_name not found
        '''
        raise NotImplementedError, 'get_pref'

    def save_pref(self, user, pref_name, pref_value):
        '''
        :param user: a :class:`User <allura.model.auth.User>`
        :param str pref_name:
        :param pref_value:
        '''
        raise NotImplementedError, 'set_pref'

    def find_by_display_name(self, name):
        '''
        :rtype: list of :class:`Users <allura.model.auth.User>`
        '''
        raise NotImplementedError, 'find_by_display_name'

class LocalUserPreferencesProvider(UserPreferencesProvider):
    '''
    The default UserPreferencesProvider, storing preferences on the User object
    in mongo.
    '''

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

    def find_by_display_name(self, name):
        from allura import model as M
        name_regex = re.compile('(?i)%s' % re.escape(name))
        users = M.User.query.find(dict(
                display_name=name_regex)).sort('username').all()
        return users
