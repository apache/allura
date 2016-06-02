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

import logging
import os
import datetime
import re

import bson
import tg
from tg import expose, flash, redirect, validate, config, session
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import tmpl_context as c, app_globals as g
from pylons import request, response
from webob import exc as wexc
from paste.deploy.converters import asbool
from urlparse import urlparse, urljoin

import allura.tasks.repo_tasks
from allura import model as M
from allura.lib import validators as V
from allura.lib.security import require_authenticated, has_access
from allura.lib import helpers as h
from allura.lib import plugin
from allura.lib.decorators import require_post
from allura.lib.repository import RepositoryApp
from allura.lib.widgets import (
    SubscriptionForm,
    OAuthApplicationForm,
    OAuthRevocationForm,
    LoginForm,
    ForgottenPasswordForm,
    DisableAccountForm)
from allura.lib.widgets import forms, form_fields as ffw
from allura.lib import mail_util
from allura.controllers import BaseController

log = logging.getLogger(__name__)


class F(object):
    login_form = LoginForm()
    password_change_form = forms.PasswordChangeForm(action='/auth/preferences/change_password')
    upload_key_form = forms.UploadKeyForm(action='/auth/preferences/upload_sshkey')
    recover_password_change_form = forms.PasswordChangeBase()
    forgotten_password_form = ForgottenPasswordForm()
    subscription_form = SubscriptionForm()
    registration_form = forms.RegistrationForm(action='/auth/save_new')
    oauth_application_form = OAuthApplicationForm(action='register')
    oauth_revocation_form = OAuthRevocationForm(
        action='/auth/preferences/revoke_oauth')
    change_personal_data_form = forms.PersonalDataForm()
    add_socialnetwork_form = forms.AddSocialNetworkForm()
    remove_socialnetwork_form = forms.RemoveSocialNetworkForm()
    add_telnumber_form = forms.AddTelNumberForm()
    add_website_form = forms.AddWebsiteForm()
    skype_account_form = forms.SkypeAccountForm()
    remove_textvalue_form = forms.RemoveTextValueForm()
    add_timeslot_form = forms.AddTimeSlotForm()
    remove_timeslot_form = forms.RemoveTimeSlotForm()
    add_inactive_period_form = forms.AddInactivePeriodForm()
    remove_inactive_period_form = forms.RemoveInactivePeriodForm()
    save_skill_form = forms.AddUserSkillForm()
    remove_skill_form = forms.RemoveSkillForm()
    disable_account_form = DisableAccountForm()


class AuthController(BaseController):

    def __init__(self):
        self.preferences = PreferencesController()
        self.user_info = UserInfoController()
        self.subscriptions = SubscriptionsController()
        self.oauth = OAuthController()
        if asbool(config.get('auth.allow_user_to_disable_account', False)):
            self.disable = DisableAccountController()

    def __getattr__(self, name):
        urls = plugin.UserPreferencesProvider.get().additional_urls()
        if name not in urls:
            raise AttributeError("'%s' object has no attribute '%s'" % (type(self).__name__, name))
        return urls[name]

    @expose()
    def prefs(self, *args, **kwargs):
        '''
        Redirect old /auth/prefs URL to /auth/subscriptions
        (to handle old email links, etc).
        '''
        redirect('/auth/subscriptions/')

    @expose('jinja:allura:templates/login.html')
    @with_trailing_slash
    def index(self, *args, **kwargs):
        orig_request = request.environ.get('pylons.original_request', None)
        if 'return_to' in kwargs:
            return_to = kwargs.pop('return_to')
        elif orig_request:
            return_to = orig_request.url
        else:
            return_to = request.referer
        c.form = F.login_form
        return dict(return_to=return_to)

    @expose('jinja:allura:templates/login_fragment.html')
    def login_fragment(self, *args, **kwargs):
        return self.index(*args, **kwargs)

    @expose('jinja:allura:templates/create_account.html')
    def create_account(self, **kw):
        if not asbool(config.get('auth.allow_user_registration', True)):
            raise wexc.HTTPNotFound()
        c.form = F.registration_form
        return dict()

    def _validate_hash(self, hash):
        login_url = config.get('auth.login_url', '/auth/')
        if not hash:
            redirect(login_url)
        user_record = M.User.query.find(
            {'tool_data.AuthPasswordReset.hash': hash}).first()
        if not user_record:
            log.info('Reset hash not found: {}'.format(hash))
            flash('Unable to process reset, please try again')
            redirect(login_url)
        hash_expiry = user_record.get_tool_data(
            'AuthPasswordReset', 'hash_expiry')
        if not hash_expiry or hash_expiry < datetime.datetime.utcnow():
            log.info('Reset hash expired: {} {}'.format(hash, hash_expiry))
            flash('Unable to process reset, please try again')
            redirect(login_url)
        return user_record

    @expose('jinja:allura:templates/forgotten_password.html')
    def forgotten_password(self, hash=None, **kw):
        provider = plugin.AuthenticationProvider.get(request)
        if not provider.forgotten_password_process:
            raise wexc.HTTPNotFound()
        user_record = None
        if not hash:
            c.forgotten_password_form = F.forgotten_password_form
        else:
            user_record = self._validate_hash(hash)
            c.recover_password_change_form = F.recover_password_change_form
        return dict(hash=hash, user_record=user_record)

    @expose()
    @require_post()
    @validate(F.recover_password_change_form, error_handler=forgotten_password)
    def set_new_password(self, hash=None, pw=None, pw2=None):
        provider = plugin.AuthenticationProvider.get(request)
        if not provider.forgotten_password_process:
            raise wexc.HTTPNotFound()
        user = self._validate_hash(hash)
        user.set_password(pw)
        user.set_tool_data('AuthPasswordReset', hash='', hash_expiry='')  # Clear password reset token
        h.auditlog_user('Password changed (through recovery process)', user=user)
        flash('Password changed')
        redirect('/auth/?return_to=/')  # otherwise the default return_to would be the forgotten_password referrer page

    @expose()
    @require_post()
    def password_recovery_hash(self, email=None, **kw):
        provider = plugin.AuthenticationProvider.get(request)
        if not provider.forgotten_password_process:
            raise wexc.HTTPNotFound()
        if not email:
            redirect('/')

        user_record = M.User.by_email_address(email)
        allow_non_primary_email_reset = asbool(config.get('auth.allow_non_primary_email_password_reset', True))

        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            flash('Enter email in correct format!','error')
            redirect('/auth/forgotten_password')

        if not allow_non_primary_email_reset:
            message = 'If the given email address is on record, '\
                      'a password reset email has been sent to the account\'s primary email address.'
            email_record = M.EmailAddress.get(email=provider.get_primary_email_address(user_record=user_record),
                                                    confirmed=True)
        else:
            message = 'A password reset email has been sent, if the given email address is on record in our system.'
            email_record = M.EmailAddress.get(email=email, confirmed=True)

        if user_record and email_record and email_record.confirmed:
            hash = h.nonce(42)
            user_record.set_tool_data('AuthPasswordReset',
                                      hash=hash,
                                      hash_expiry=datetime.datetime.utcnow() +
                                      datetime.timedelta(seconds=int(config.get('auth.recovery_hash_expiry_period', 600))))

            log.info('Sending password recovery link to %s', email_record.email)
            subject = '%s Password recovery' % config['site_name']
            text = g.jinja2_env.get_template('allura:templates/mail/forgot_password.txt').render(dict(
                user=user_record,
                config=config,
                hash=hash,
            ))

            allura.tasks.mail_tasks.sendsimplemail.post(
                toaddr=email_record.email,
                fromaddr=config['forgemail.return_path'],
                reply_to=config['forgemail.return_path'],
                subject=subject,
                message_id=h.gen_message_id(),
                text=text)
        h.auditlog_user('Password recovery link sent to: %s', email, user=user_record)
        flash(message)
        redirect('/')

    @expose()
    @require_post()
    @validate(F.registration_form, error_handler=create_account)
    def save_new(self, display_name=None, username=None, pw=None, email=None, **kw):
        if not asbool(config.get('auth.allow_user_registration', True)):
            raise wexc.HTTPNotFound()
        require_email = asbool(config.get('auth.require_email_addr', False))
        make_project = not require_email
        user = M.User.register(
            dict(username=username,
                 display_name=display_name,
                 password=pw,
                 pending=require_email), make_project)
        user.set_tool_data('allura', pwd_reset_preserve_session=session.id)
        # else the first password set causes this session to be invalidated
        if require_email:
            em = user.claim_address(email)
            if em:
                em.send_verification_link()
            flash('User "%s" registered. Verification link was sent to your email.' % username)
        else:
            plugin.AuthenticationProvider.get(request).login(user)
            flash('User "%s" registered' % username)
        redirect('/')

    @expose()
    def send_verification_link(self, a):
        addr = M.EmailAddress.get(email=a, claimed_by_user_id=c.user._id)
        confirmed_emails = M.EmailAddress.find(dict(email=a, confirmed=True)).all()
        confirmed_emails = filter(lambda item: item != addr, confirmed_emails)

        if addr:
            if any(email.confirmed for email in confirmed_emails):
                addr.send_claim_attempt()
            else:
                addr.send_verification_link()
            flash('Verification link sent')
        else:
            flash('No such address', 'error')
        redirect(request.referer)

    def _verify_addr(self, addr):
        confirmed_by_other = M.EmailAddress.find(dict(email=addr.email, confirmed=True)).all() if addr else []
        confirmed_by_other = filter(lambda item: item != addr, confirmed_by_other)

        if addr and not confirmed_by_other:
            addr.confirmed = True
            user = addr.claimed_by_user(include_pending=True)
            flash('Email address confirmed')
            h.auditlog_user('Email address verified: %s',  addr.email, user=user)
            if(user.get_pref('email_address') == None):
                user.set_pref('email_address', addr.email)
            if user.pending:
                plugin.AuthenticationProvider.get(request).activate_user(user)
                projectname = plugin.AuthenticationProvider.get(request).user_project_shortname(user)
                n = M.Neighborhood.query.get(name='Users')
                n.register_project(projectname, user=user, user_project=True)
        else:
            flash('Unknown verification link', 'error')

    @expose()
    def verify_addr(self, a):
        addr = M.EmailAddress.get(nonce=a)
        self._verify_addr(addr)
        redirect('/auth/preferences/')

    @expose()
    def logout(self):
        plugin.AuthenticationProvider.get(request).logout()
        redirect(config.get('auth.post_logout_url', '/'))

    @expose()
    @require_post()
    @validate(F.login_form, error_handler=index)
    def do_login(self, return_to=None, **kw):
        location = '/'

        if session.get('expired-username'):
            if return_to and return_to not in plugin.AuthenticationProvider.pwd_expired_allowed_urls:
                location = tg.url(plugin.AuthenticationProvider.pwd_expired_allowed_urls[0], dict(return_to=return_to))
            else:
                location = tg.url(plugin.AuthenticationProvider.pwd_expired_allowed_urls[0])
        elif return_to and return_to != request.url:
            rt_host = urlparse(urljoin(config['base_url'], return_to)).netloc
            base_host = urlparse(config['base_url']).netloc
            if rt_host == base_host:
                location = return_to

        redirect(location)

    @expose(content_type='text/plain')
    def refresh_repo(self, *repo_path):
        # post-commit hooks use this
        if not repo_path:
            return 'No repo specified'
        repo_path = '/' + '/'.join(repo_path)
        project, rest = h.find_project(repo_path)
        if project is None:
            return 'No project at %s' % repo_path
        if not rest:
            return '%s does not include a repo mount point' % repo_path
        h.set_context(project.shortname,
                      rest[0], neighborhood=project.neighborhood)
        if c.app is None or not getattr(c.app, 'repo'):
            return 'Cannot find repo at %s' % repo_path
        allura.tasks.repo_tasks.refresh.post()
        return '%r refresh queued.\n' % c.app.repo

    def _auth_repos(self, user):
        def _unix_group_name(neighborhood, shortname):
            path = neighborhood.url_prefix + \
                shortname[len(neighborhood.shortname_prefix):]
            parts = [p for p in path.split('/') if p]
            if len(parts) == 2 and parts[0] == 'p':
                parts = parts[1:]
            return '.'.join(reversed(parts))

        repos = []
        for p in user.my_projects():
            for p in [p] + p.direct_subprojects:
                for app in p.app_configs:
                    if not issubclass(g.entry_points["tool"][app.tool_name], RepositoryApp):
                        continue
                    if not has_access(app, 'write', user, p):
                        continue
                    repos.append('/%s/%s/%s' % (
                        app.tool_name.lower(),
                        _unix_group_name(p.neighborhood, p.shortname),
                        app.options['mount_point']))
        repos.sort()
        return repos

    @expose('json:')
    def repo_permissions(self, repo_path=None, username=None, **kw):
        """Expects repo_path to be a filesystem path like
            <tool>/<project>.<neighborhood>/reponame[.git]
        unless the <neighborhood> is 'p', in which case it is
            <tool>/<project>/reponame[.git]

        Returns JSON describing this user's permissions on that repo.
        """
        disallow = dict(allow_read=False, allow_write=False,
                        allow_create=False)
        # Find the user
        user = M.User.by_username(username)
        if not user:
            response.status = 404
            return dict(disallow, error='unknown user')
        if not repo_path:
            return dict(allow_write=self._auth_repos(user))

        parts = [p for p in repo_path.split(os.path.sep) if p]
        # strip the tool name
        parts = parts[1:]
        if '.' in parts[0]:
            project, neighborhood = parts[0].split('.')
        else:
            project, neighborhood = parts[0], 'p'
        parts = [neighborhood, project] + parts[1:]
        project_path = '/' + '/'.join(parts)
        project, rest = h.find_project(project_path)
        if project is None:
            log.info("Can't find project at %s from repo_path %s",
                     project_path, repo_path)
            response.status = 404
            return dict(disallow, error='unknown project')
        c.project = project
        c.app = project.app_instance(rest[0])
        if not c.app:
            c.app = project.app_instance(os.path.splitext(rest[0])[0])
        if c.app is None:
            log.info("Can't find repo at %s on repo_path %s",
                     rest[0], repo_path)
            return disallow
        return dict(allow_read=has_access(c.app, 'read')(user=user),
                    allow_write=has_access(c.app, 'write')(user=user),
                    allow_create=has_access(c.app, 'create')(user=user))

    @expose('jinja:allura:templates/pwd_expired.html')
    @without_trailing_slash
    def pwd_expired(self, **kw):
        require_authenticated()
        c.form = F.password_change_form
        return {'return_to': kw.get('return_to')}

    @expose()
    @require_post()
    @without_trailing_slash
    @validate(V.NullValidator(), error_handler=pwd_expired)
    def pwd_expired_change(self, **kw):
        require_authenticated()
        return_to = kw.get('return_to')
        kw = F.password_change_form.to_python(kw, None)
        ap = plugin.AuthenticationProvider.get(request)
        try:
            expired_username = session.get('expired-username')
            expired_user = M.User.query.get(username=expired_username) if expired_username else None
            ap.set_password(expired_user or c.user, kw['oldpw'], kw['pw'])
            expired_user.set_tool_data('allura', pwd_reset_preserve_session=session.id)
            expired_user.set_tool_data('AuthPasswordReset', hash='', hash_expiry='')  # Clear password reset token

        except wexc.HTTPUnauthorized:
            flash('Incorrect password', 'error')
            redirect(tg.url('/auth/pwd_expired', dict(return_to=return_to)))
        flash('Password changed')
        session.pop('pwd-expired', None)
        session['username'] = session.get('expired-username')
        session.pop('expired-username', None)

        session.save()
        h.auditlog_user('Password reset (via expiration process)')
        if return_to and return_to != request.url:
            redirect(return_to)
        else:
            redirect('/')


def select_new_primary_addr(user, ignore_emails=[]):
    for obj_e in user.email_addresses:
        obj = user.address_object(obj_e)
        if obj and obj.confirmed and obj_e not in ignore_emails:
            return obj_e


class PreferencesController(BaseController):

    def _check_security(self):
        require_authenticated()

    @with_trailing_slash
    @expose('jinja:allura:templates/user_prefs.html')
    def index(self, **kw):
        c.enter_password = ffw.Lightbox(name='enter_password')
        c.password_change_form = F.password_change_form
        c.upload_key_form = F.upload_key_form
        provider = plugin.AuthenticationProvider.get(request)
        menu = provider.account_navigation()
        return dict(menu=menu, user=c.user)

    def _update_emails(self, user, admin=False, form_params={}):
        # not using **kw in method signature, to ensure 'admin' can't be passed in via a form submit
        kw = form_params
        addr = kw.pop('addr', None)
        new_addr = kw.pop('new_addr', None)
        primary_addr = kw.pop('primary_addr', None)
        provider = plugin.AuthenticationProvider.get(request)
        for i, (old_a, data) in enumerate(zip(user.email_addresses, addr or [])):
            obj = user.address_object(old_a)
            if data.get('delete') or not obj:
                if not admin and (not kw.get('password') or not provider.validate_password(user, kw.get('password'))):
                    flash('You must provide your current password to delete an email', 'error')
                    return
                if primary_addr == user.email_addresses[i]:
                    if select_new_primary_addr(user, ignore_emails=primary_addr) is None \
                            and asbool(config.get('auth.require_email_addr', False)):
                        flash('You must have at least one verified email address.', 'error')
                        return
                    else:
                        # clear it now, a new one will get set below
                        user.set_pref('email_address', None)
                        primary_addr = None
                        user.set_tool_data('AuthPasswordReset', hash='', hash_expiry='')
                h.auditlog_user('Email address deleted: %s', user.email_addresses[i], user=user)
                del user.email_addresses[i]
                if obj:
                    obj.delete()
        if new_addr.get('claim') or new_addr.get('addr'):
            user.set_tool_data('AuthPasswordReset', hash='', hash_expiry='')  # Clear password reset token
            claimed_emails_limit = config.get('user_prefs.maximum_claimed_emails', None)
            if claimed_emails_limit and len(user.email_addresses) >= int(claimed_emails_limit):
                flash('You cannot claim more than %s email addresses.' % claimed_emails_limit, 'error')
                return
            if not admin and (not kw.get('password') or not provider.validate_password(user, kw.get('password'))):
                flash('You must provide your current password to claim new email', 'error')
                return

            claimed_emails = M.EmailAddress.find({'email': new_addr['addr']}).all()

            if any(email.claimed_by_user_id == user._id for email in claimed_emails):
                flash('Email address already claimed', 'error')

            elif mail_util.isvalid(new_addr['addr']):
                em = M.EmailAddress.create(new_addr['addr'])
                if em:
                    user.email_addresses.append(em.email)
                    em.claimed_by_user_id = user._id

                    confirmed_emails = filter(lambda email: email.confirmed, claimed_emails)
                    if not confirmed_emails:
                        if not admin:
                            em.send_verification_link()
                        else:
                            AuthController()._verify_addr(em)
                    else:
                        em.send_claim_attempt()

                    if not admin:
                        user.set_tool_data('AuthPasswordReset', hash='', hash_expiry='')
                        flash('A verification email has been sent.  Please check your email and click to confirm.')

                    h.auditlog_user('New email address: %s', new_addr['addr'], user=user)
                else:
                    flash('Email address %s is invalid' % new_addr['addr'], 'error')
            else:
                flash('Email address %s is invalid' % new_addr['addr'], 'error')
        if not primary_addr and not user.get_pref('email_address') and user.email_addresses:
            primary_addr = select_new_primary_addr(user)
        if primary_addr:
            if user.get_pref('email_address') != primary_addr:
                if not admin and (not kw.get('password') or not provider.validate_password(user, kw.get('password'))):
                    flash('You must provide your current password to change primary address', 'error')
                    return
                h.auditlog_user(
                    'Primary email changed: %s => %s',
                    user.get_pref('email_address'),
                    primary_addr,
                    user=user)
            user.set_pref('email_address', primary_addr)
            user.set_tool_data('AuthPasswordReset', hash='', hash_expiry='')

    @h.vardec
    @expose()
    @require_post()
    def update_emails(self, **kw):
        if asbool(config.get('auth.allow_edit_prefs', True)):
            self._update_emails(c.user, form_params=kw)
        redirect('.')

    @h.vardec
    @expose()
    @require_post()
    def update(self, preferences=None, **kw):
        if asbool(config.get('auth.allow_edit_prefs', True)):
            if not preferences.get('display_name'):
                flash("Display Name cannot be empty.", 'error')
                redirect('.')
            old = c.user.get_pref('display_name')
            c.user.set_pref('display_name', preferences['display_name'])
            if old != preferences['display_name']:
                h.auditlog_user('Display Name changed %s => %s', old, preferences['display_name'])
            for k, v in preferences.iteritems():
                if k == 'results_per_page':
                    v = int(v)
                c.user.set_pref(k, v)
        redirect('.')

    @expose()
    @require_post()
    @validate(V.NullValidator(), error_handler=index)
    def change_password(self, **kw):
        kw = F.password_change_form.to_python(kw, None)
        ap = plugin.AuthenticationProvider.get(request)
        try:
            ap.set_password(c.user, kw['oldpw'], kw['pw'])
            c.user.set_tool_data('allura', pwd_reset_preserve_session=session.id)
            c.user.set_tool_data('AuthPasswordReset', hash='', hash_expiry='')

        except wexc.HTTPUnauthorized:
            flash('Incorrect password', 'error')
            redirect('.')
        flash('Password changed')
        h.auditlog_user('Password changed')
        redirect('.')

    @expose()
    @require_post()
    def upload_sshkey(self, key=None):
        ap = plugin.AuthenticationProvider.get(request)
        try:
            ap.upload_sshkey(c.user.username, key)
        except AssertionError, ae:
            flash('Error uploading key: %s' % ae, 'error')
        flash('Key uploaded')
        redirect('.')

    @expose()
    @require_post()
    def user_message(self, allow_user_messages=False):
        c.user.set_pref('disable_user_messages', not allow_user_messages)
        redirect(request.referer)


class UserInfoController(BaseController):

    def __init__(self, *args, **kwargs):
        self.skills = UserSkillsController()
        self.contacts = UserContactsController()
        self.availability = UserAvailabilityController()

    def _check_security(self):
        require_authenticated()

    @with_trailing_slash
    @expose('jinja:allura:templates/user_info.html')
    def index(self, **kw):
        provider = plugin.AuthenticationProvider.get(request)
        menu = provider.account_navigation()
        return dict(menu=menu)

    @expose()
    @require_post()
    @validate(F.change_personal_data_form, error_handler=index)
    def change_personal_data(self, **kw):
        require_authenticated()
        c.user.set_pref('sex', kw['sex'])
        c.user.set_pref('birthdate', kw.get('birthdate'))
        localization = {'country': kw.get('country'), 'city': kw.get('city')}
        c.user.set_pref('localization', localization)
        c.user.set_pref('timezone', kw['timezone'])

        flash('Your personal data was successfully updated!')
        redirect('.')


class UserSkillsController(BaseController):

    def __init__(self, category=None):
        self.category = category
        super(UserSkillsController, self).__init__()

    def _check_security(self):
        require_authenticated()

    @expose()
    def _lookup(self, trove_cat_id, *remainder):
        cat = M.TroveCategory.query.get(trove_cat_id=int(trove_cat_id))
        if not cat:
            raise wexc.HTTPNotFound
        return UserSkillsController(category=cat), remainder

    @with_trailing_slash
    @expose('jinja:allura:templates/user_skills.html')
    def index(self, **kw):
        l = []
        parents = []
        if kw.get('selected_category') is not None:
            selected_skill = M.TroveCategory.query.get(
                trove_cat_id=int(kw.get('selected_category')))
        elif self.category:
            selected_skill = self.category
        else:
            l = M.TroveCategory.query.find(
                dict(trove_parent_id=0, show_as_skill=True)).all()
            selected_skill = None
        if selected_skill:
            l = [scat for scat in selected_skill.subcategories
                 if scat.show_as_skill]
            temp_cat = selected_skill.parent_category
            while temp_cat:
                parents = [temp_cat] + parents
                temp_cat = temp_cat.parent_category
        provider = plugin.AuthenticationProvider.get(request)
        menu = provider.account_navigation()
        return dict(
            skills_list=l,
            selected_skill=selected_skill,
            parents=parents,
            menu=menu,
            add_details_fields=(len(l) == 0))

    @expose()
    @require_post()
    @validate(F.save_skill_form, error_handler=index)
    def save_skill(self, **kw):
        trove_id = int(kw.get('selected_skill'))
        category = M.TroveCategory.query.get(trove_cat_id=trove_id)

        new_skill = dict(
            category_id=category._id,
            level=kw.get('level'),
            comment=kw.get('comment'))

        s = [skill for skill in c.user.skills
             if str(skill.category_id) != str(new_skill['category_id'])]
        s.append(new_skill)
        c.user.set_pref('skills', s)
        flash('Your skills list was successfully updated!')
        redirect('.')

    @expose()
    @require_post()
    @validate(F.remove_skill_form, error_handler=index)
    def remove_skill(self, **kw):
        trove_id = int(kw.get('categoryid'))
        category = M.TroveCategory.query.get(trove_cat_id=trove_id)

        s = [skill for skill in c.user.skills
             if str(skill.category_id) != str(category._id)]
        c.user.set_pref('skills', s)
        flash('Your skills list was successfully updated!')
        redirect('.')


class UserContactsController(BaseController):

    def _check_security(self):
        require_authenticated()

    @with_trailing_slash
    @expose('jinja:allura:templates/user_contacts.html')
    def index(self, **kw):
        provider = plugin.AuthenticationProvider.get(request)
        menu = provider.account_navigation()
        return dict(menu=menu)

    @expose()
    @require_post()
    @validate(F.add_socialnetwork_form, error_handler=index)
    def add_social_network(self, **kw):
        require_authenticated()
        c.user.add_socialnetwork(kw['socialnetwork'], kw['accounturl'])
        flash('Your personal contacts were successfully updated!')
        redirect('.')

    @expose()
    @require_post()
    @validate(F.remove_socialnetwork_form, error_handler=index)
    def remove_social_network(self, **kw):
        require_authenticated()
        c.user.remove_socialnetwork(kw['socialnetwork'], kw['account'])
        flash('Your personal contacts were successfully updated!')
        redirect('.')

    @expose()
    @require_post()
    @validate(F.add_telnumber_form, error_handler=index)
    def add_telnumber(self, **kw):
        require_authenticated()
        c.user.add_telephonenumber(kw['newnumber'])
        flash('Your personal contacts were successfully updated!')
        redirect('.')

    @expose()
    @require_post()
    @validate(F.remove_textvalue_form, error_handler=index)
    def remove_telnumber(self, **kw):
        require_authenticated()
        c.user.remove_telephonenumber(kw['oldvalue'])
        flash('Your personal contacts were successfully updated!')
        redirect('.')

    @expose()
    @require_post()
    @validate(F.add_website_form, error_handler=index)
    def add_webpage(self, **kw):
        require_authenticated()
        c.user.add_webpage(kw['newwebsite'])
        flash('Your personal contacts were successfully updated!')
        redirect('.')

    @expose()
    @require_post()
    @validate(F.remove_textvalue_form, error_handler=index)
    def remove_webpage(self, **kw):
        require_authenticated()
        c.user.remove_webpage(kw['oldvalue'])
        flash('Your personal contacts were successfully updated!')
        redirect('.')

    @expose()
    @require_post()
    @validate(F.skype_account_form, error_handler=index)
    def skype_account(self, **kw):
        require_authenticated()
        c.user.set_pref('skypeaccount', kw['skypeaccount'])
        flash('Your personal contacts were successfully updated!')
        redirect('.')


class UserAvailabilityController(BaseController):

    def _check_security(self):
        require_authenticated()

    @with_trailing_slash
    @expose('jinja:allura:templates/user_availability.html')
    def index(self, **kw):
        provider = plugin.AuthenticationProvider.get(request)
        menu = provider.account_navigation()
        return dict(menu=menu)

    @expose()
    @require_post()
    @validate(F.add_timeslot_form, error_handler=index)
    def add_timeslot(self, **kw):
        require_authenticated()
        c.user.add_timeslot(kw['weekday'], kw['starttime'], kw['endtime'])
        flash('Your availability timeslots were successfully updated!')
        redirect('.')

    @expose()
    @require_post()
    @validate(F.remove_timeslot_form, error_handler=index)
    def remove_timeslot(self, **kw):
        require_authenticated()
        c.user.remove_timeslot(kw['weekday'], kw['starttime'], kw['endtime'])
        flash('Your availability timeslots were successfully updated!')
        redirect('.')

    @expose()
    @require_post()
    @validate(F.add_inactive_period_form, error_handler=index)
    def add_inactive_period(self, **kw):
        require_authenticated()
        c.user.add_inactive_period(kw['startdate'], kw['enddate'])
        flash('Your inactivity periods were successfully updated!')
        redirect('.')

    @expose()
    @require_post()
    @validate(F.remove_inactive_period_form, error_handler=index)
    def remove_inactive_period(self, **kw):
        require_authenticated()
        c.user.remove_inactive_period(kw['startdate'], kw['enddate'])
        flash('Your availability timeslots were successfully updated!')
        redirect('.')


class SubscriptionsController(BaseController):
    """ Gives users the ability to manage subscriptions to tools. """

    def _check_security(self):
        require_authenticated()

    @with_trailing_slash
    @expose('jinja:allura:templates/user_subs.html')
    def index(self, **kw):
        """ The subscription selection page in user preferences.

        Builds up a list of dictionaries, each containing subscription
        information about a tool.
        """
        c.form = F.subscription_form
        c.revoke_access = F.oauth_revocation_form

        subscriptions = []
        mailboxes = list(M.Mailbox.query.find(
            dict(user_id=c.user._id, is_flash=False)))
        projects = dict(
            (p._id, p) for p in M.Project.query.find(dict(
                _id={'$in': [mb.project_id for mb in mailboxes]})))
        app_index = dict(
            (ac._id, ac) for ac in M.AppConfig.query.find(dict(
                _id={'$in': [mb.app_config_id for mb in mailboxes]})))

        # Add the tools that are already subscribed to by the user.
        for mb in mailboxes:
            project = projects.get(mb.project_id, None)
            app_config = app_index.get(mb.app_config_id, None)
            if project is None:
                mb.query.delete()
                continue
            if app_config is None:
                continue
            app = app_config.load()
            if not app.has_notifications:
                continue

            subscriptions.append(dict(
                subscription_id=mb._id,
                project_id=project._id,
                app_config_id=mb.app_config_id,
                project_name=project.name,
                tool=app_config.options['mount_label'],
                artifact_title=dict(
                    text='Everything' if mb.artifact_title == 'All artifacts' else mb.artifact_title,
                    href=mb.artifact_url),
                topic=mb.topic,
                type=mb.type,
                frequency=mb.frequency.unit,
                artifact=mb.artifact_index_id,
                subscribed=True))

        # Dictionary of all projects projects accessible based on a users credentials (user_roles).
        my_projects = dict((p._id, p) for p in c.user.my_projects())

        # Dictionary containing all tools (subscribed and un-subscribed).
        my_tools = M.AppConfig.query.find(dict(
            project_id={'$in': my_projects.keys()}))

        # Dictionary containing all the currently subscribed tools for a given user.
        my_tools_subscriptions = dict(
            (mb.app_config_id, mb) for mb in M.Mailbox.query.find(dict(
                user_id=c.user._id,
                project_id={'$in': projects.keys()},
                app_config_id={'$in': app_index.keys()},
                artifact_index_id=None)))

        # Add the remaining tools that are eligible for subscription.
        for tool in my_tools:
            if tool['_id'] in my_tools_subscriptions:
                continue  # We have already subscribed to this tool.
            app = tool.load()
            if not app.has_notifications:
                continue

            subscriptions.append(
                dict(tool_id=tool._id,
                     user_id=c.user._id,
                     project_id=tool.project_id,
                     project_name=my_projects[tool.project_id].name,
                     tool=tool.options['mount_label'],
                     artifact_title='Everything',
                     topic=None,
                     type=None,
                     frequency=None,
                     artifact=None))

        subscriptions.sort(key=lambda d: (d['project_name'], d['tool']))
        provider = plugin.AuthenticationProvider.get(request)
        menu = provider.account_navigation()
        return dict(
            subscriptions=subscriptions,
            menu=menu)

    @h.vardec
    @expose()
    @require_post()
    @validate(F.subscription_form, error_handler=index)
    def update_subscriptions(self, subscriptions=None, email_format=None, **kw):
        for s in subscriptions:
            if s['subscribed']:
                if s['tool_id'] and s['project_id']:
                    M.Mailbox.subscribe(
                        project_id=bson.ObjectId(s['project_id']),
                        app_config_id=bson.ObjectId(s['tool_id']))
            else:
                if s['subscription_id'] is not None:
                    s['subscription_id'].delete()
        if email_format:
            c.user.set_pref('email_format', email_format)

        redirect(request.referer)


class OAuthController(BaseController):

    def _check_security(self):
        require_authenticated()

    @with_trailing_slash
    @expose('jinja:allura:templates/oauth_applications.html')
    def index(self, **kw):
        c.form = F.oauth_application_form
        consumer_tokens = M.OAuthConsumerToken.for_user(c.user)
        access_tokens = M.OAuthAccessToken.for_user(c.user)
        provider = plugin.AuthenticationProvider.get(request)
        return dict(
            menu=provider.account_navigation(),
            consumer_tokens=consumer_tokens,
            access_tokens=access_tokens,
        )

    @expose()
    @require_post()
    @validate(F.oauth_application_form, error_handler=index)
    def register(self, application_name=None, application_description=None, **kw):
        M.OAuthConsumerToken(name=application_name,
                             description=application_description)
        flash('OAuth Application registered')
        redirect('.')

    @expose()
    @require_post()
    def deregister(self, _id=None):
        app = M.OAuthConsumerToken.query.get(_id=bson.ObjectId(_id))
        if app is None:
            flash('Invalid app ID', 'error')
            redirect('.')
        if app.user_id != c.user._id:
            flash('Invalid app ID', 'error')
            redirect('.')
        M.OAuthRequestToken.query.remove({'consumer_token_id': app._id})
        M.OAuthAccessToken.query.remove({'consumer_token_id': app._id})
        app.delete()
        flash('Application deleted')
        redirect('.')

    @expose()
    @require_post()
    def generate_access_token(self, _id):
        """
        Manually generate an OAuth access token for the given consumer.

        NB: Manually generated access tokens are bearer tokens, which are
        less secure (since they rely only on the token, which is transmitted
        with each request, unlike the access token secret).
        """
        consumer_token = M.OAuthConsumerToken.query.get(_id=bson.ObjectId(_id))
        if consumer_token is None:
            flash('Invalid app ID', 'error')
            redirect('.')
        if consumer_token.user_id != c.user._id:
            flash('Invalid app ID', 'error')
            redirect('.')
        request_token = M.OAuthRequestToken(
            consumer_token_id=consumer_token._id,
            user_id=c.user._id,
            callback='manual',
            validation_pin=h.nonce(20),
            is_bearer=True,
        )
        M.OAuthAccessToken(
            consumer_token_id=consumer_token._id,
            request_token_id=c.user._id,
            user_id=request_token.user_id,
            is_bearer=True,
        )
        redirect('.')

    @expose()
    @require_post()
    def revoke_access_token(self, _id):
        access_token = M.OAuthAccessToken.query.get(_id=bson.ObjectId(_id))
        if access_token is None:
            flash('Invalid token ID', 'error')
            redirect('.')
        if access_token.user_id != c.user._id:
            flash('Invalid token ID', 'error')
            redirect('.')
        access_token.delete()
        flash('Token revoked')
        redirect('.')


class DisableAccountController(BaseController):

    def _check_security(self):
        require_authenticated()

    @with_trailing_slash
    @expose('jinja:allura:templates/user_disable_account.html')
    def index(self, **kw):
        provider = plugin.AuthenticationProvider.get(request)
        menu = provider.account_navigation()
        my_projects = c.user.my_projects_by_role_name('Admin')
        return {
            'menu': menu,
            'my_projects': my_projects,
            'form': F.disable_account_form,
        }

    @expose()
    @require_post()
    @validate(F.disable_account_form, error_handler=index)
    def do_disable(self, password):
        provider = plugin.AuthenticationProvider.get(request)
        provider.disable_user(c.user)
        flash('Your account was successfully disabled!')
        redirect('/')
