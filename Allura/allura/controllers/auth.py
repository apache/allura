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

import logging, string, os
from urllib import urlencode
import datetime

import bson
from tg import expose, session, flash, redirect, validate, config
from tg.decorators import with_trailing_slash
from pylons import tmpl_context as c, app_globals as g
from pylons import request, response
from webob import exc as wexc

import allura.tasks.repo_tasks
from allura import model as M
from allura.model.project import TroveCategory
from allura.lib import validators as V
from allura.lib.oid_helper import verify_oid, process_oid
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
    ForgottenPasswordForm)
from allura.lib.widgets import forms
from allura.lib import exceptions as exc
from allura.controllers import BaseController

log = logging.getLogger(__name__)

OID_PROVIDERS=[
    ('OpenID', '${username}'),
    ('Yahoo!', 'http://yahoo.com'),
    ('Google', 'https://www.google.com/accounts/o8/id'),
    ('MyOpenID', 'http://${username}.myopenid.com/'),
    ('LiveJournal', 'http://${username}.livejournal.com/'),
    ('Flickr', 'http://www.filckr.com/photos/${username}/'),
    ('Wordpress', 'http://${username}.wordpress.com/'),
    ('Blogger', 'http://${username}.blogspot.com/'),
    ('Vidoop', 'http://${username}.myvidoop.com/'),
    ('Verisign', 'http://${username}.pip.verisignlabs.com/'),
    ('ClaimID', 'http://openid.claimid.com/${username}/'),
    ('AOL', 'http://openid.aol.com/${username}/') ]

class F(object):
    login_form = LoginForm()
    recover_password_change_form = forms.PasswordChangeBase()
    forgotten_password_form = ForgottenPasswordForm()
    subscription_form=SubscriptionForm()
    registration_form = forms.RegistrationForm(action='/auth/save_new')
    oauth_application_form = OAuthApplicationForm(action='register')
    oauth_revocation_form = OAuthRevocationForm(action='/auth/preferences/revoke_oauth')
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

class AuthController(BaseController):

    def __init__(self):
        self.preferences = PreferencesController()
        self.user_info = UserInfoController()
        self.subscriptions = SubscriptionsController()
        self.oauth = OAuthController()

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
        return dict(oid_providers=OID_PROVIDERS, return_to=return_to)

    @expose('jinja:allura:templates/login_fragment.html')
    def login_fragment(self, *args, **kwargs):
        return self.index(*args, **kwargs)

    @expose('jinja:allura:templates/custom_login.html')
    def login_verify_oid(self, provider, username, return_to=None):
        if provider:
            oid_url = string.Template(provider).safe_substitute(
                username=username)
        else:
            oid_url = username
        return verify_oid(oid_url, failure_redirect='.',
                          return_to='login_process_oid?%s' % urlencode(dict(return_to=return_to)),
                          title='OpenID Login',
                          prompt='Click below to continue')

    @expose()
    def login_process_oid(self, **kw):
        oid_obj = process_oid(failure_redirect='.')
        c.user = oid_obj.claimed_by_user()
        session['userid'] = c.user._id
        session.save()
        if not c.user.username:
            flash('Please choose a user name for SourceForge, %s.'
                  % c.user.get_pref('display_name'))
            redirect('setup_openid_user')
        redirect(kw.pop('return_to', '/'))

    @expose('jinja:allura:templates/bare_openid.html')
    def bare_openid(self, url=None):
        '''Called to notify the user that they must set up a 'real' (with
        username) account when they have a pure openid account'''
        return dict(location=url)

    @expose('jinja:allura:templates/setup_openid_user.html')
    def setup_openid_user(self):
        return dict()

    @expose('jinja:allura:templates/create_account.html')
    def create_account(self, **kw):
        c.form = F.registration_form
        return dict()

    @expose('jinja:allura:templates/forgotten_password.html')
    @validate(F.recover_password_change_form, error_handler=index)
    def forgotten_password(self, hash=None, **kw):
        provider = plugin.AuthenticationProvider.get(request)
        if not provider:
            redirect('/')
        if not hash:
            c.forgotten_password_form = F.forgotten_password_form
        else:
            c.recover_password_change_form = F.recover_password_change_form
            user_record = M.User.query.find({'tool_data.AuthPasswordReset.hash': hash}).first()
            if not user_record:
                flash('Hash was not found')
                redirect('/')
            hash_expiry = user_record.get_tool_data('AuthPasswordReset', 'hash_expiry')
            if not hash_expiry or hash_expiry < datetime.datetime.utcnow():
                flash('Hash time was expired.')
                redirect('/')
            if request.method == 'POST':
                provider.set_password(user_record, None, kw['pw'])
                user_record.set_tool_data('AuthPasswordReset', hash='', hash_expiry='')
                flash('Password changed')
                redirect('/auth/')
        return dict()

    @expose()
    @require_post()
    @validate(F.forgotten_password_form, error_handler=forgotten_password)
    def password_recovery_hash(self, email=None, **kw):
        if not email:
            redirect('/')
        user_record = M.User.by_email_address(email)
        hash = h.nonce(42)
        user_record.set_tool_data('AuthPasswordReset',
                                  hash=hash,
                                  hash_expiry=datetime.datetime.utcnow() +
                                  datetime.timedelta(seconds=int(config.get('auth.recovery_hash_expiry_period', 600))))

        log.info('Sending password recovery link to %s', email)
        text = '''
To reset your password on %s, please visit the following URL:

%s/auth/forgotten_password/%s

''' % (config['site_name'], config['base_url'], hash)

        allura.tasks.mail_tasks.sendmail.post(
            destinations=[email],
            fromaddr=config['forgemail.return_path'],
            reply_to='',
            subject='Password recovery',
            message_id=h.gen_message_id(),
            text=text)

        flash('Email with instructions has been sent.')
        redirect('/')

    @expose()
    @require_post()
    @validate(F.registration_form, error_handler=create_account)
    def save_new(self, display_name=None, username=None, pw=None, **kw):
        user = M.User.register(
            dict(username=username,
                 display_name=display_name,
                 password=pw))
        plugin.AuthenticationProvider.get(request).login(user)
        flash('User "%s" registered' % user.get_pref('display_name'))
        redirect('/')

    @expose()
    def send_verification_link(self, a):
        addr = M.EmailAddress.query.get(_id=a)
        if addr:
            addr.send_verification_link()
            flash('Verification link sent')
        else:
            flash('No such address', 'error')
        redirect(request.referer)

    @expose()
    def verify_addr(self, a):
        addr = M.EmailAddress.query.get(nonce=a)
        if addr:
            addr.confirmed = True
            flash('Email address confirmed')
        else:
            flash('Unknown verification link', 'error')
        redirect('/')

    @expose()
    @require_post()
    def do_setup_openid_user(self, username=None, display_name=None):
        u = M.User.by_username(username)
        if u and username != c.user.username:
            flash('That username is already taken.  Please choose another.',
                  'error')
            redirect('setup_openid_user')
        c.user.username = username
        c.user.set_pref('display_name', display_name)
        if u is None:
            n = M.Neighborhood.query.get(name='Users')
            n.register_project('u/' + username, user_project=True)
        flash('Your username has been set to %s.' % username)
        redirect('/')

    @expose('jinja:allura:templates/claim_openid.html')
    def claim_oid(self):
        return dict(oid_providers=OID_PROVIDERS)

    @expose('jinja:allura:templates/custom_login.html')
    def claim_verify_oid(self, provider, username):
        if provider:
            oid_url = string.Template(provider).safe_substitute(
                username=username)
        else:
            oid_url = username
        return verify_oid(oid_url, failure_redirect='claim_oid',
                          return_to='claim_process_oid',
                          title='Claim OpenID',
                          prompt='Click below to continue')

    @expose()
    @require_post()
    def claim_process_oid(self, **kw):
        oid_obj = process_oid(failure_redirect='claim_oid')
        if c.user:
            c.user.claim_openid(oid_obj._id)
            flash('Claimed %s' % oid_obj._id)
        redirect('/auth/preferences/')

    @expose()
    def logout(self):
        plugin.AuthenticationProvider.get(request).logout()
        if config.get('auth.method', 'local') == 'sfx':
            redirect(g.logout_url)
        else:
            redirect('/')

    @expose()
    @require_post()
    @validate(F.login_form, error_handler=index)
    def do_login(self, return_to=None, **kw):
        if return_to and return_to != request.url:
            redirect(return_to)
        redirect('/')

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
        h.set_context(project.shortname, rest[0], neighborhood=project.neighborhood)
        if c.app is None or not getattr(c.app, 'repo'):
            return 'Cannot find repo at %s' % repo_path
        allura.tasks.repo_tasks.refresh.post()
        return '%r refresh queued.\n' % c.app.repo


    def _auth_repos(self, user):
        def _unix_group_name(neighborhood, shortname):
            'shameless copied from sfx_api.py'
            path = neighborhood.url_prefix + shortname[len(neighborhood.shortname_prefix):]
            parts = [ p for p in path.split('/') if p ]
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
        disallow = dict(allow_read=False, allow_write=False, allow_create=False)
        # Find the user
        user = M.User.by_username(username)
        if not user:
            response.status=404
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
        parts = [ neighborhood, project ] + parts[1:]
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

class PreferencesController(BaseController):

    def _check_security(self):
        require_authenticated()

    @with_trailing_slash
    @expose('jinja:allura:templates/user_prefs.html')
    def index(self, **kw):
        provider = plugin.AuthenticationProvider.get(request)
        menu = provider.account_navigation()
        api_token = M.ApiToken.query.get(user_id=c.user._id)
        return dict(
                menu=menu,
                api_token=api_token,
            )

    @h.vardec
    @expose()
    @require_post()
    def update(self,
               addr=None,
               new_addr=None,
               primary_addr=None,
               oid=None,
               new_oid=None,
               preferences=None,
               **kw):
        if config.get('auth.method', 'local') == 'local':
            if not preferences.get('display_name'):
                flash("Display Name cannot be empty.",'error')
                redirect('.')
            c.user.set_pref('display_name', preferences['display_name'])
            for i, (old_a, data) in enumerate(zip(c.user.email_addresses, addr or [])):
                obj = c.user.address_object(old_a)
                if data.get('delete') or not obj:
                    del c.user.email_addresses[i]
                    if obj: obj.delete()
            c.user.set_pref('email_address', primary_addr)
            if new_addr.get('claim'):
                if M.EmailAddress.query.get(_id=new_addr['addr'], confirmed=True):
                    flash('Email address already claimed', 'error')
                else:
                    c.user.email_addresses.append(new_addr['addr'])
                    em = M.EmailAddress.upsert(new_addr['addr'])
                    em.claimed_by_user_id=c.user._id
                    em.send_verification_link()
            for i, (old_oid, data) in enumerate(zip(c.user.open_ids, oid or [])):
                obj = c.user.openid_object(old_oid)
                if data.get('delete') or not obj:
                    del c.user.open_ids[i]
                    if obj: obj.delete()
            for k,v in preferences.iteritems():
                if k == 'results_per_page':
                    v = int(v)
                c.user.set_pref(k, v)
        redirect('.')

    @expose()
    @require_post()
    def gen_api_token(self):
        tok = M.ApiToken.query.get(user_id=c.user._id)
        if tok is None:
            tok = M.ApiToken(user_id=c.user._id)
        else:
            tok.secret_key = h.cryptographic_nonce()
        redirect(request.referer)

    @expose()
    @require_post()
    def del_api_token(self):
        tok = M.ApiToken.query.get(user_id=c.user._id)
        if tok is None: return
        tok.delete()
        redirect(request.referer)

    @expose()
    @require_post()
    @validate(V.NullValidator(), error_handler=index)
    def change_password(self, **kw):
        kw = g.theme.password_change_form.to_python(kw, None)
        ap = plugin.AuthenticationProvider.get(request)
        try:
            ap.set_password(c.user, kw['oldpw'], kw['pw'])
        except wexc.HTTPUnauthorized:
            flash('Incorrect password', 'error')
            redirect('.')
        flash('Password changed')
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
        localization={'country':kw.get('country'), 'city':kw.get('city')}
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
    def _lookup(self, catshortname, *remainder):
        cat = M.TroveCategory.query.get(shortname=catshortname)
        return UserSkillsController(category=cat), remainder

    @with_trailing_slash
    @expose('jinja:allura:templates/user_skills.html')
    def index(self, **kw):
        l = []
        parents = []
        if kw.get('selected_category') is not None:
            selected_skill = M.TroveCategory.query.get(trove_cat_id=int(kw.get('selected_category')))
        elif self.category:
            selected_skill = self.category
        else:
            l = M.TroveCategory.query.find(dict(trove_parent_id=0, show_as_skill=True)).all()
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
            skills_list = l,
            selected_skill = selected_skill,
            parents = parents,
            menu = menu,
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

    def _check_security(self):
        require_authenticated()

    @with_trailing_slash
    @expose('jinja:allura:templates/user_subs.html')
    def index(self, **kw):
        c.form = F.subscription_form
        c.revoke_access = F.oauth_revocation_form
        subscriptions = []
        mailboxes = M.Mailbox.query.find(dict(user_id=c.user._id, is_flash=False))
        mailboxes = list(mailboxes.ming_cursor)
        project_collection = M.Project.query.mapper.collection
        app_collection = M.AppConfig.query.mapper.collection
        projects = dict(
            (p._id, p) for p in project_collection.m.find(dict(
                    _id={'$in': [mb.project_id for mb in mailboxes ]})))
        app_index = dict(
            (ac._id, ac) for ac in app_collection.m.find(dict(
                    _id={'$in': [mb.app_config_id for mb in mailboxes]})))

        for mb in mailboxes:
            project = projects.get(mb.project_id, None)
            app_config = app_index.get(mb.app_config_id, None)
            if project is None:
                mb.m.delete()
                continue
            if app_config is None:
                continue
            subscriptions.append(dict(
                    subscription_id=mb._id,
                    project_name=project.name,
                    mount_point=app_config.options['mount_point'],
                    artifact_title=dict(text=mb.artifact_title, href=mb.artifact_url),
                    topic=mb.topic,
                    type=mb.type,
                    frequency=mb.frequency.unit,
                    artifact=mb.artifact_index_id,
                    subscribed=True))

        my_projects = dict((p._id, p) for p in c.user.my_projects())
        my_tools = app_collection.m.find(dict(
            project_id={'$in': my_projects.keys()}))
        for tool in my_tools:
            p_id = tool.project_id
            subscribed = M.Mailbox.subscribed(
                    project_id=p_id, app_config_id=tool._id)
            if not subscribed:
                subscriptions.append(dict(
                    tool_id=tool._id,
                    project_id=p_id,
                    project_name=my_projects[p_id].name,
                    mount_point=tool.options['mount_point'],
                    artifact_title='No subscription',
                    topic=None,
                    type=None,
                    frequency=None,
                    artifact=None))
        subscriptions.sort(key=lambda d: (d['project_name'], d['mount_point']))
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
        M.OAuthConsumerToken(name=application_name, description=application_description)
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
        access_token = M.OAuthAccessToken(
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
