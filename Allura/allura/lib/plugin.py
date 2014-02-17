#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

'''
Allura plugins for authentication and project registration
'''
import re
import os
import logging
import subprocess
import string
from urllib2 import urlopen
from cStringIO import StringIO
from random import randint
from hashlib import sha256
from base64 import b64encode
from datetime import datetime, timedelta
import json

try:
    import ldap
    from ldap import modlist
except ImportError:
    ldap = modlist = None
import pkg_resources
from tg import config
from pylons import tmpl_context as c, app_globals as g
from webob import exc
from bson.tz_util import FixedOffset
from paste.deploy.converters import asbool, asint

from ming.utils import LazyProperty
from ming.orm import state
from ming.orm import ThreadLocalORMSession

from allura.lib import helpers as h
from allura.lib import security
from allura.lib import exceptions as forge_exc

log = logging.getLogger(__name__)


class AuthenticationProvider(object):

    '''
    An interface to provide authentication services for Allura.

    To use a new provider, expose an entry point in setup.py::

        [allura.auth]
        myprovider = foo.bar:MyAuthProvider

    Then in your .ini file, set ``auth.method=myprovider``
    '''

    forgotten_password_process = False

    def __init__(self, request):
        self.request = request

    @classmethod
    def get(cls, request):
        '''returns the AuthenticationProvider instance for this request'''
        try:
            result = cls._loaded_ep
        except AttributeError:
            method = config.get('auth.method', 'local')
            result = cls._loaded_ep = g.entry_points['auth'][method]
        return result(request)

    @LazyProperty
    def session(self):
        return self.request.environ['beaker.session']

    def authenticate_request(self):
        from allura import model as M
        user = M.User.query.get(_id=self.session.get('userid', None))
        if user is None:
            return M.User.anonymous()
        if user.disabled:
            self.logout()
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
            if user is None:
                user = self._login()
            self.session['userid'] = user._id
            self.session.save()
            g.zarkov_event('login', user=user)
            g.statsUpdater.addUserLogin(user)
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

    def account_navigation(self):
        return [
            {
                'tabid': 'account_user_prefs',
                'title': 'Preferences',
                'target': "/auth/preferences",
                'alt': 'Manage Personal Preferences',
            },
            {
                'tabid': 'account_user_info',
                'title': 'Personal Info',
                'target': "/auth/user_info",
                'alt': 'Manage Personal Information',
            },
            {
                'tabid': 'account_subscriptions',
                'title': 'Subscriptions',
                'target': "/auth/subscriptions",
                'alt': 'Manage Subscription Preferences',
            },
            {
                'tabid': 'account_oauth',
                'title': 'OAuth',
                'target': "/auth/oauth",
                'alt': 'Manage OAuth Preferences',
            },
        ]

    @LazyProperty
    def account_urls(self):
        return {m['tabid']: m['target'] for m in self.account_navigation()}

    def user_project_shortname(self, user):
        '''
        :param user: a :class:`User <allura.model.auth.User>`
        :rtype: str
        '''
        raise NotImplementedError, 'user_project_shortname'

    def user_by_project_shortname(self, shortname):
        '''
        :param str: shortname
        :rtype: user: a :class:`User <allura.model.auth.User>`
        '''
        raise NotImplementedError, 'user_by_project_shortname'

    def update_notifications(self, user):
        raise NotImplemented, 'update_notifications'

    def user_registration_date(self, user):
        '''
        Returns the date in which a user registered himself/herself on the forge.

        :param user: a :class:`User <allura.model.auth.User>`
        :rtype: :class:`datetime <datetime.datetime>`
        '''
        raise NotImplementedError, 'user_registration_date'


class LocalAuthenticationProvider(AuthenticationProvider):

    '''
    Stores user passwords on the User model, in mongo.  Uses per-user salt and
    SHA-256 encryption.
    '''

    forgotten_password_process = True

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
        if user is None:
            return False
        if not user.password:
            return False
        salt = str(user.password[6:6 + user.SALT_LEN])
        check = self._encode_password(password, salt)
        if check != user.password:
            return False
        return True

    def by_username(self, username):
        from allura import model as M
        un = re.escape(username)
        un = un.replace(r'\_', '[-_]')
        un = un.replace(r'\-', '[-_]')
        rex = re.compile('^' + un + '$')
        return M.User.query.get(username=rex, disabled=False)

    def set_password(self, user, old_password, new_password):
        user.password = self._encode_password(new_password)

    def _encode_password(self, password, salt=None):
        from allura import model as M
        if salt is None:
            salt = ''.join(chr(randint(1, 0x7f))
                           for i in xrange(M.User.SALT_LEN))
        hashpass = sha256(salt + password.encode('utf-8')).digest()
        return 'sha256' + salt + b64encode(hashpass)

    def user_project_shortname(self, user):
        return 'u/' + user.username.replace('_', '-')

    def user_by_project_shortname(self, shortname):
        from allura import model as M
        return M.User.query.get(username=shortname, disabled=False)

    def update_notifications(self, user):
        return ''

    def user_registration_date(self, user):
        if user._id:
            return user._id.generation_time
        return datetime.utcnow()


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
                objectClass=['account', 'posixAccount'],
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

            if asbool(config.get('auth.ldap.use_schroot', True)):
                argv = ('schroot -d / -c %s -u root /ldap-userconfig.py init %s' % (
                    config['auth.ldap.schroot_name'], user_doc['username'])).split()
                p = subprocess.Popen(
                    argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                rc = p.wait()
                if rc != 0:
                    log.error('Error creating home directory for %s',
                              user_doc['username'])
        except:
            raise
        return result

    def upload_sshkey(self, username, pubkey):
            if not asbool(config.get('auth.ldap.use_schroot', True)):
                raise NotImplemented, 'SSH keys are not supported'

            argv = ('schroot -d / -c %s -u root /ldap-userconfig.py upload %s' % (
                config['auth.ldap.schroot_name'], username)).split() + [pubkey]
            p = subprocess.Popen(
                argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            rc = p.wait()
            if rc != 0:
                errmsg = p.stdout.read()
                log.exception('Error uploading public SSH key for %s: %s',
                              username, errmsg)
                assert False, errmsg

    def by_username(self, username):
        from allura import model as M
        return M.User.query.get(username=username, disabled=False)

    def set_password(self, user, old_password, new_password):
        try:
            dn = 'uid=%s,%s' % (user.username, config['auth.ldap.suffix'])
            con = ldap.initialize(config['auth.ldap.server'])
            con.bind_s(dn, old_password.encode('utf-8'))
            con.modify_s(
                dn, [(ldap.MOD_REPLACE, 'userPassword', new_password.encode('utf-8'))])
            con.unbind_s()
        except ldap.INVALID_CREDENTIALS:
            raise exc.HTTPUnauthorized()

    def _login(self):
        from allura import model as M
        user = M.User.query.get(
            username=self.request.params['username'], disabled=False)
        if user is None:
            raise exc.HTTPUnauthorized()
        try:
            dn = 'uid=%s,%s' % (user.username, config['auth.ldap.suffix'])
            con = ldap.initialize(config['auth.ldap.server'])
            con.bind_s(dn, self.request.params['password'])
            con.unbind_s()
        except ldap.INVALID_CREDENTIALS:
            raise exc.HTTPUnauthorized()
        return user

    def user_project_shortname(self, user):
        return 'u/' + user.username.replace('_', '-')

    def user_by_project_shortname(self, shortname):
        from allura import model as M
        return M.User.query.get(username=shortname)

    def user_registration_date(self, user):
        if user._id:
            return user._id.generation_time
        return datetime.utcnow()


class ProjectRegistrationProvider(object):

    '''
    Project registration services for Allura.  This is a full implementation
    and the default.  Extend this class with your own if you need to add more
    functionality.

    To use a new provider, expose an entry point in setup.py::

        [allura.project_registration]
        myprovider = foo.bar:MyAuthProvider

    Then in your .ini file, set registration.method=myprovider

    The provider should expose an attribute, `shortname_validator` which is
    an instance of a FormEncode validator that validates project shortnames.
    The `to_python()` method of the validator should accept a `check_allowed`
    argument to indicate whether additional checks beyond correctness of the
    name should be done, such as whether the name is already in use.
    '''

    def __init__(self):
        from allura.lib.widgets import forms
        self.add_project_widget = forms.NeighborhoodAddProjectForm
        self.shortname_validator = forms.NeighborhoodProjectShortNameValidator(
        )

    @classmethod
    def get(cls):
        from allura.lib import app_globals
        method = config.get('registration.method', 'local')
        return app_globals.Globals().entry_points['registration'][method]()

    def suggest_name(self, project_name, neighborhood):
        """Return a suggested project shortname for the full ``project_name``.

        Example: "My Great Project" -> "mygreatproject"

        """
        return re.sub("[^A-Za-z0-9]", "", project_name).lower()

    def rate_limit(self, user, neighborhood):
        """Check the various config-defined project registration rate
        limits, and if any are exceeded, raise ProjectRatelimitError.

        """
        if security.has_access(neighborhood, 'admin', user=user)():
            return
        # have to have the replace because, despite being UTC,
        # the result from utcnow() is still offset-naive  :-(
        # maybe look into making the mongo connection offset-naive?
        now = datetime.utcnow().replace(tzinfo=FixedOffset(0, 'UTC'))
        project_count = len(list(user.my_projects()))
        rate_limits = json.loads(config.get('project.rate_limits', '{}'))
        for rate, count in rate_limits.items():
            user_age = now - user._id.generation_time
            user_age = (user_age.microseconds +
                        (user_age.seconds + user_age.days * 24 * 3600) * 10 ** 6) / 10 ** 6
            if user_age < int(rate) and project_count >= count:
                raise forge_exc.ProjectRatelimitError()

    def register_neighborhood_project(self, neighborhood, users, allow_register=False):
        from allura import model as M
        shortname = '--init--'
        name = 'Home Project for %s' % neighborhood.name
        p = M.Project(neighborhood_id=neighborhood._id,
                      shortname=shortname,
                      name=name,
                      short_description='',
                      description=(
                          'You can edit this description in the admin page'),
                      homepage_title = '# ' + name,
                      last_updated = datetime.utcnow(),
                      is_nbhd_project=True,
                      is_root=True)
        try:
            p.configure_project(
                users=users,
                is_user_project=False,
                apps=[
                    ('Wiki', 'wiki', 'Wiki'),
                    ('admin', 'admin', 'Admin')])
        except:
            ThreadLocalORMSession.close_all()
            log.exception('Error registering project %s' % p)
            raise
        if allow_register:
            role_auth = M.ProjectRole.authenticated(p)
            security.simple_grant(p.acl, role_auth._id, 'register')
            state(p).soil()
        return p

    def register_project(self, neighborhood, shortname, project_name, user, user_project, private_project, apps=None):
        '''Register a new project in the neighborhood.  The given user will
        become the project's superuser.
        '''
        self.validate_project(neighborhood, shortname,
                              project_name, user, user_project, private_project)
        return self._create_project(neighborhood, shortname, project_name, user, user_project, private_project, apps)

    def validate_project(self, neighborhood, shortname, project_name, user, user_project, private_project):
        '''
        Validate that a project can be registered, before it is
        '''
        from allura import model as M

        # Check for private project rights
        if neighborhood.features['private_projects'] == False and private_project:
            raise ValueError(
                "You can't create private projects for %s neighborhood" %
                neighborhood.name)

        # Check for project limit creation
        nb_max_projects = neighborhood.get_max_projects()
        if nb_max_projects is not None:
            count = M.Project.query.find(dict(
                neighborhood_id=neighborhood._id,
                deleted=False,
                is_nbhd_project=False,
            )).count()
            if count >= nb_max_projects:
                log.exception('Error registering project %s' % project_name)
                raise forge_exc.ProjectOverlimitError()

        self.rate_limit(user, neighborhood)

        if user_project and shortname.startswith('u/'):
            check_shortname = shortname.replace('u/', '', 1)
        else:
            check_shortname = shortname
        self.shortname_validator.to_python(
            check_shortname, neighborhood=neighborhood)

        p = M.Project.query.get(
            shortname=shortname, neighborhood_id=neighborhood._id)
        if p:
            raise forge_exc.ProjectConflict(
                '%s already exists in nbhd %s' % (shortname, neighborhood._id))

    def _create_project(self, neighborhood, shortname, project_name, user, user_project, private_project, apps):
        '''
        Actually create the project, no validation.  This should not be called directly
        under normal circumstances.
        '''
        from allura import model as M

        project_template = neighborhood.get_project_template()
        p = M.Project(neighborhood_id=neighborhood._id,
                      shortname=shortname,
                      name=project_name,
                      short_description='',
                      description=(
                          'You can edit this description in the admin page'),
                      homepage_title=shortname,
                      last_updated = datetime.utcnow(),
                      is_nbhd_project=False,
                      is_root=True)
        p.configure_project(
            users=[user],
            is_user_project=user_project,
            is_private_project=private_project or project_template.get(
                'private', False),
            apps=apps or [] if 'tools' in project_template else None)

        # Setup defaults from neighborhood project template if applicable
        offset = p.next_mount_point(include_hidden=True)
        if 'groups' in project_template:
            for obj in project_template['groups']:
                name = obj.get('name')
                permissions = set(obj.get('permissions', [])) & \
                    set(p.permissions)
                usernames = obj.get('usernames', [])
                # Must provide a group name
                if not name:
                    continue
                # If the group already exists, we'll add users to it,
                # but we won't change permissions on the group
                group = M.ProjectRole.by_name(name, project=p)
                if not group:
                    # If creating a new group, *must* specify permissions
                    if not permissions:
                        continue
                    group = M.ProjectRole(project_id=p._id, name=name)
                    p.acl += [M.ACE.allow(group._id, perm)
                              for perm in permissions]
                for username in usernames:
                    guser = M.User.by_username(username)
                    if not (guser and guser._id):
                        continue
                    pr = M.ProjectRole.by_user(guser, project=p, upsert=True)
                    if group._id not in pr.roles:
                        pr.roles.append(group._id)
        if 'tools' in project_template:
            for i, tool in enumerate(project_template['tools'].keys()):
                tool_config = project_template['tools'][tool]
                tool_options = tool_config.get('options', {})
                for k, v in tool_options.iteritems():
                    if isinstance(v, basestring):
                        tool_options[k] = \
                            string.Template(v).safe_substitute(
                                p.__dict__.get('root_project', {}))
                if p.app_instance(tool) is None:
                    app = p.install_app(tool,
                                        mount_label=tool_config['label'],
                                        mount_point=tool_config['mount_point'],
                                        ordinal=i + offset,
                                        **tool_options)
                    if tool == 'wiki':
                        from forgewiki import model as WM
                        text = tool_config.get('home_text',
                                               '[[members limit=20]]\n[[download_button]]')
                        WM.Page.query.get(
                            app_config_id=app.config._id).text = text

        if 'tool_order' in project_template:
            for i, tool in enumerate(project_template['tool_order']):
                p.app_config(tool).options.ordinal = i
        if 'labels' in project_template:
            p.labels = project_template['labels']
        if 'trove_cats' in project_template:
            for trove_type in project_template['trove_cats'].keys():
                troves = getattr(p, 'trove_%s' % trove_type)
                for trove_id in project_template['trove_cats'][trove_type]:
                    troves.append(
                        M.TroveCategory.query.get(trove_cat_id=trove_id)._id)
        if 'icon' in project_template:
            icon_file = StringIO(
                urlopen(project_template['icon']['url']).read())
            M.ProjectFile.save_image(
                project_template['icon']['filename'], icon_file,
                square=True, thumbnail_size=(48, 48),
                thumbnail_meta=dict(project_id=p._id, category='icon'))

        if user_project:
            # Allow for special user-only tools
            p._extra_tool_status = ['user']
            # add user project informative text to home
            from forgewiki import model as WM
            home_app = p.app_instance('wiki')
            home_page = WM.Page.query.get(app_config_id=home_app.config._id)
            home_page.text = ("This is the personal project of %s."
                              " This project is created automatically during user registration"
                              " as an easy place to store personal data that doesn't need its own"
                              " project such as cloned repositories.") % user.display_name

        # clear the RoleCache for the user so this project will
        # be picked up by user.my_projects()
        g.credentials.clear_user(user._id, None)  # unnamed roles for this user
        # named roles for this project + user
        g.credentials.clear_user(user._id, p._id)
        with h.push_config(c, project=p, user=user):
            ThreadLocalORMSession.flush_all()
            # have to add user to context, since this may occur inside auth code
            # for user-project reg, and c.user isn't set yet
            g.post_event('project_created')
        return p

    def register_subproject(self, project, name, user, install_apps, project_name=None):
        from allura import model as M
        assert h.re_project_name.match(name), 'Invalid subproject shortname'
        shortname = project.shortname + '/' + name
        ordinal = int(project.ordered_mounts(include_hidden=True)
                      [-1]['ordinal']) + 1
        sp = M.Project(
            parent_id=project._id,
            neighborhood_id=project.neighborhood_id,
            shortname=shortname,
            name=project_name or name,
            last_updated=datetime.utcnow(),
            is_root=False,
            ordinal=ordinal,
        )
        with h.push_config(c, project=sp):
            M.AppConfig.query.remove(dict(project_id=c.project._id))
            if install_apps:
                sp.install_app('admin', 'admin', ordinal=1)
                sp.install_app('search', 'search', ordinal=2)
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

    To use a new provider, expose an entry point in setup.py::

        [allura.theme]
        myprovider = foo.bar:MyThemeProvider

    Then in your .ini file, set theme=mytheme

    The variables referencing jinja template files can be changed to point at your
    own jinja templates.  Use the standard templates as a reference, you should
    provide matching macros and block names.

    :var icons: a dictionary of sized icons for each tool
    '''

    master_template = 'allura:templates/jinja_master/master.html'
    jinja_macros = 'allura:templates/jinja_master/theme_macros.html'
    nav_menu = 'allura:templates/jinja_master/nav_menu.html'
    top_nav = 'allura:templates/jinja_master/top_nav.html'
    sidebar_menu = 'allura:templates/jinja_master/sidebar_menu.html'
    icons = {
        'subproject': {
            24: 'images/ext_24.png',
            32: 'images/ext_32.png',
            48: 'images/ext_48.png'
        }
    }

    def require(self):
        g.register_theme_css('css/site_style.css', compress=False)
        g.register_theme_css('css/allura.css', compress=False)

    @classmethod
    def register_ew_resources(cls, manager, name):
        manager.register_directory(
            'theme/%s' % name,
            pkg_resources.resource_filename(
                'allura',
                os.path.join('nf', name)))

    @LazyProperty
    def password_change_form(self):
        '''
        :return: None, or an easywidgets Form to render on the user preferences page
        '''
        from allura.lib.widgets.forms import PasswordChangeForm
        return PasswordChangeForm(action='/auth/preferences/change_password')

    @LazyProperty
    def personal_data_form(self):
        '''
        :return: None, or an easywidgets Form to render on the user preferences page
        '''
        from allura.lib.widgets.forms import PersonalDataForm
        return PersonalDataForm()

    @LazyProperty
    def add_telnumber_form(self):
        '''
        :return: None, or an easywidgets Form to render on the user preferences page to
                 allow adding a telephone number.
        '''
        from allura.lib.widgets.forms import AddTelNumberForm
        return AddTelNumberForm()

    @LazyProperty
    def add_website_form(self):
        '''
        :return: None, or an easywidgets Form to render on the user preferences page to
                 allow adding a personal website url.
        '''
        from allura.lib.widgets.forms import AddWebsiteForm
        return AddWebsiteForm()

    @LazyProperty
    def skype_account_form(self):
        '''
        :return: None, or an easywidgets Form to render on the user preferences page to
                 allow setting the user's Skype account.
        '''
        from allura.lib.widgets.forms import SkypeAccountForm
        return SkypeAccountForm()

    @LazyProperty
    def remove_textvalue_form(self):
        '''
        :return: None, or an easywidgets Form to render on the user preferences page to
                 allow removing a single text value from a list.
        '''
        from allura.lib.widgets.forms import RemoveTextValueForm
        return RemoveTextValueForm()

    @LazyProperty
    def add_socialnetwork_form(self):
        '''
        :return: None, or an easywidgets Form to render on  the user preferences page to
                 allow adding a social network account.
        '''
        from allura.lib.widgets.forms import AddSocialNetworkForm
        return AddSocialNetworkForm(action='/auth/preferences/add_social_network')

    @LazyProperty
    def remove_socialnetwork_form(self):
        '''
        :return: None, or an easywidgets Form to render on  the user preferences page to
                 allow removing a social network account.
        '''
        from allura.lib.widgets.forms import RemoveSocialNetworkForm
        return RemoveSocialNetworkForm(action='/auth/preferences/remove_social_network')

    @LazyProperty
    def add_timeslot_form(self):
        '''
        :return: None, or an easywidgets Form to render on the user preferences page
                 to allow creating a new availability timeslot
        '''
        from allura.lib.widgets.forms import AddTimeSlotForm
        return AddTimeSlotForm()

    @LazyProperty
    def remove_timeslot_form(self):
        '''
        :return: None, or an easywidgets Form to render on the user preferences page
                 to remove a timeslot
        '''
        from allura.lib.widgets.forms import RemoveTimeSlotForm
        return RemoveTimeSlotForm()

    @LazyProperty
    def add_inactive_period_form(self):
        '''
        :return: None, or an easywidgets Form to render on the user preferences page
                 to allow creating a new period of inactivity
        '''
        from allura.lib.widgets.forms import AddInactivePeriodForm
        return AddInactivePeriodForm()

    @LazyProperty
    def remove_inactive_period_form(self):
        '''
        :return: None, or an easywidgets Form to render on the user preferences page
                 to allow removing an existing period of inactivity
        '''
        from allura.lib.widgets.forms import RemoveInactivePeriodForm
        return RemoveInactivePeriodForm()

    @LazyProperty
    def add_trove_category(self):
        '''
        :return: None, or an easywidgets Form to render on the page to create a
                 new trove_category
        '''
        from allura.lib.widgets.forms import AddTroveCategoryForm
        return AddTroveCategoryForm(action='/categories/create')

    @LazyProperty
    def remove_trove_category(self):
        '''
        :return: None, or an easywidgets Form to render on the page to remove
                 an existing trove_category
        '''
        from allura.lib.widgets.forms import RemoveTroveCategoryForm
        return RemoveTroveCategoryForm(action='/categories/remove')

    @LazyProperty
    def add_user_skill(self):
        '''
        :return: None, or an easywidgets Form to render on the page to add a
                 new skill to a user profile
        '''
        from allura.lib.widgets.forms import AddUserSkillForm
        return AddUserSkillForm(action='/auth/user_info/skills/save_skill')

    @LazyProperty
    def select_subcategory_form(self):
        '''
        :return: None, or an easywidgets Form to render on the page to add a
                 new skill to a user profile, allowing to select a category in
                 order to see its sub-categories
        '''
        from allura.lib.widgets.forms import SelectSubCategoryForm
        return SelectSubCategoryForm(action='/auth/user_info/skills/')

    @LazyProperty
    def remove_user_skill(self):
        '''
        :return: None, or an easywidgets Form to render on the page to remove
                 an existing skill from a user profile
        '''
        from allura.lib.widgets.forms import RemoveSkillForm
        return RemoveSkillForm(action='/auth/user_info/skills/remove_skill')

    @LazyProperty
    def upload_key_form(self):
        '''
        :return: None, or an easywidgets Form to render on the user preferences page
        '''
        from allura.lib.widgets.forms import UploadKeyForm
        return UploadKeyForm(action='/auth/preferences/upload_sshkey')

    @property
    def master(self):
        return self.master_template

    @classmethod
    def get(cls):
        name = config.get('theme', 'allura')
        return g.entry_points['theme'][name]()

    def app_icon_url(self, app, size):
        """returns the default icon for the given app (or non-app thing like 'subproject').
            Takes an instance of class Application, or else a string.
            Expected to be overriden by derived Themes.
        """
        if isinstance(app, unicode):
            app = str(app)
        if isinstance(app, str):
            if app in self.icons and size in self.icons[app]:
                return g.theme_href(self.icons[app][size])
            elif app in g.entry_points['tool']:
                return g.entry_points['tool'][app].icon_url(size)
            else:
                return None
        else:
            return app.icon_url(size)

    def get_site_notification(self):
        from pylons import request, response
        from allura.model.notification import SiteNotification
        note = SiteNotification.current()
        if note is None:
            return None
        cookie = request.cookies.get('site-notification', '').split('-')
        if len(cookie) == 3 and cookie[0] == str(note._id):
            views = asint(cookie[1]) + 1
            closed = asbool(cookie[2])
        else:
            views = 1
            closed = False
        if closed or note.impressions > 0 and views > note.impressions:
            return None
        response.set_cookie(
            'site-notification',
            '-'.join(map(str, [note._id, views, closed])),
            max_age=timedelta(days=365))
        return note


class LocalProjectRegistrationProvider(ProjectRegistrationProvider):
    pass


class UserPreferencesProvider(object):

    '''
    An interface for user preferences, like display_name and email_address

    To use a new provider, expose an entry point in setup.py::

        [allura.user_prefs]
        myprefs = foo.bar:MyUserPrefProvider

    Then in your .ini file, set user_prefs_storage.method=myprefs
    '''

    @classmethod
    def get(cls):
        method = config.get('user_prefs_storage.method', 'local')
        return g.entry_points['user_prefs'][method]()

    def get_pref(self, user, pref_name):
        '''
        :param user: a :class:`User <allura.model.auth.User>`
        :param str pref_name:
        :return: pref_value
        :raises: AttributeError if pref_name not found
        '''
        raise NotImplementedError, 'get_pref'

    def set_pref(self, user, pref_name, pref_value):
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

    def additional_urls(self):
        '''
        :return: [[str url, function], ]
        '''
        return []


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


class AdminExtension(object):

    """
    A base class for extending the admin areas in Allura.

    After extending this, expose the app by adding an entry point in your
    setup.py::

        [allura.admin]
        myadmin = foo.bar.baz:MyCustomAdmin

    :ivar dict project_admin_controllers: Mapping of str (url component) to
        Controllers.  Can be implemented as a ``@property`` function.  The str
        url components will be mounted at /p/someproject/admin/ext/STR/ and will
        invoke the Controller.
    """

    project_admin_controllers = {}

    def update_project_sidebar_menu(self, sidebar_links):
        """
        Implement this function to modify the project sidebar.
        Check `c.project` if you want to limit when this displays
        (e.g. nbhd project, subproject, etc)

        :param sidebar_links: project admin side bar links
        :type sidebar_links: list of :class:`allura.app.SitemapEntry`

        :rtype: ``None``
        """
        pass


class SiteAdminExtension(object):
    """
    A base class for extending the site admin area in Allura.

    After extending this, expose the extension by adding an entry point in your
    setup.py::

        [allura.site_admin]
        myext = foo.bar.baz:MySiteAdminExtension

    :ivar dict controllers: Mapping of str (url component) to
        Controllers.  Can be implemented as a ``@property`` function.  The str
        url components will be mounted at /nf/admin/STR/ and will
        invoke the Controller.
    """

    controllers = {}

    def update_sidebar_menu(self, sidebar_links):
        """
        Change the site admin sidebar by modifying ``sidebar_links``.

        :param sidebar_links: site admin side bar links
        :type sidebar_links: list of :class:`allura.app.SitemapEntry`

        :rtype: ``None``
        """
        pass


class ImportIdConverter(object):

    '''
    An interface to convert to and from import_id values for indexing,
    searching, or displaying.

    To provide a new converter, expose an entry point in setup.py:

        [allura.import_id_converter]
        mysource = foo.bar:SourceIdConverter

    Then in your .ini file, set import_id_converter=mysource
    '''

    @classmethod
    def get(cls):
        converter = config.get('import_id_converter')
        if converter:
            return g.entry_points['allura.import_id_converter'][converter]()
        return cls()

    def simplify(self, import_id):
        if hasattr(import_id, 'get'):
            return import_id.get('source_id')
        return None

    def expand(self, source_id, app_instance):
        import_id = {
            'source_id': source_id,
        }
        import_id.update(app_instance.config.options.get('import_id', {}))
        return import_id
