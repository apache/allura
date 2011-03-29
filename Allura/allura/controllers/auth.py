import logging, string, os
from urllib import urlencode

import bson
from tg import expose, session, redirect, validate, config
from tg.decorators import with_trailing_slash, without_trailing_slash
from tg import c, g, request, response
from webob import exc as wexc

import allura.tasks.repo_tasks
from allura import model as M
from allura.lib import validators as V
from allura.lib.oid_helper import verify_oid, process_oid
from allura.lib.security import require_authenticated, has_access
from allura.lib import helpers as h
from allura.lib import plugin
from allura.lib.decorators import require_post
from allura.lib.widgets import SubscriptionForm, OAuthApplicationForm, OAuthRevocationForm, LoginForm
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
    subscription_form=SubscriptionForm()
    registration_form = forms.RegistrationForm(action='/auth/save_new')
    oauth_application_form = OAuthApplicationForm(action='register')
    oauth_revocation_form = OAuthRevocationForm(action='revoke_oauth')

class AuthController(BaseController):

    def __init__(self):
        self.prefs = PreferencesController()
        self.oauth = OAuthController()

    @expose('jinja:allura:templates/login.html')
    @with_trailing_slash
    def index(self, *args, **kwargs):
        orig_request = request.environ.get('tg.original_request', None)
        if 'return_to' in kwargs:
            return_to = kwargs.pop('return_to')
        elif orig_request:
            return_to = orig_request.url
        else:
            return_to = request.referer
        c.form = F.login_form
        return dict(oid_providers=OID_PROVIDERS, return_to=return_to)

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
            n.register_project('u/' + username)
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
        redirect('/auth/prefs/')

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

    @expose()
    def refresh_repo(self, *repo_path):
        if not repo_path:
            return 'No repo specified'
        repo_path = '/' + '/'.join(repo_path)
        project, rest = h.find_project(repo_path)
        if project is None:
            return 'No project at %s' % repo_path
        if not rest:
            return '%s does not include a repo mount point' % repo_path
        h.set_context(project.shortname, rest[0])
        if c.app is None or not getattr(c.app, 'repo'):
            return 'Cannot find repo at %s' % repo_path
        allura.tasks.repo_tasks.refresh.post()
        return '%r refresh queued.\n' % c.app.repo

    @expose('json:')
    def repo_permissions(self, repo_path=None, username=None, **kw):
        """Expects repo_path to be a filesystem path like
            <tool>/<project>.<neighborhood>/reponame[.git]
        unless the <neighborhood> is 'p', in which case it is
            <tool>/<project>/reponame[.git]

        Returns JSON describing this user's permissions on that repo.
        """
        disallow = dict(allow_read=False, allow_write=False, allow_create=False)
        if not repo_path:
            response.status=400
            return dict(disallow, error='no path specified')
        # Find the user
        user = M.User.by_username(username)
        if not user:
            response.status=404
            return dict(disallow, error='unknown user')
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
        mount_point = os.path.splitext(rest[0])[0]
        c.project = project
        c.app = project.app_instance(mount_point)
        if c.app is None:
            log.info("Can't find repo at %s on repo_path %s",
                     mount_point, repo_path)
            return disallow
        return dict(allow_read=has_access(c.app, 'read')(user=user),
                    allow_write=has_access(c.app, 'write')(user=user),
                    allow_create=has_access(c.app, 'create')(user=user))

class PreferencesController(BaseController):

    @with_trailing_slash
    @expose('jinja:allura:templates/user_preferences.html')
    def index(self, **kw):
        require_authenticated()
        c.form = F.subscription_form
        c.revoke_access = F.oauth_revocation_form
        subscriptions = []
        for mb in M.Mailbox.query.find(dict(user_id=c.user._id)):
            try:
                with h.push_context(mb.project_id):
                    if mb.app_config:
                        title = mb.artifact_title
                        if mb.artifact_url:
                            title = '<a href="%s">%s</a>' % (mb.artifact_url,title)
                        subscriptions.append(dict(
                                _id=mb._id,
                                project_name=mb.project.name,
                                mount_point=mb.app_config.options.mount_point,
                                artifact_title=title,
                                topic=mb.topic,
                                type=mb.type,
                                frequency=mb.frequency.unit,
                                artifact=mb.artifact_index_id))
            except exc.NoSuchProjectError:
                mb.delete() # project went away
        api_token = M.ApiToken.query.get(user_id=c.user._id)
        return dict(
            subscriptions=subscriptions,
            api_token=api_token,
            authorized_applications=M.OAuthAccessToken.for_user(c.user))

    @h.vardec
    @expose()
    @require_post()
    def update(self,
               display_name=None,
               addr=None,
               new_addr=None,
               primary_addr=None,
               oid=None,
               new_oid=None,
               preferences=None,
               **kw):
        require_authenticated()
        if display_name is None:
            flash("Display Name cannot be empty.",'error')
            redirect('.')
        if config.get('auth.method', 'local') == 'local':
            c.user.set_pref('display_name', display_name)
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
        
    @h.vardec
    @expose()
    @require_post()
    @validate(F.subscription_form, error_handler=index)
    def update_subscriptions(self, subscriptions=None, **kw):
        for s in subscriptions:
            if s['unsubscribe']:
                s['_id'].delete()
        redirect(request.referer)

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
    def revoke_oauth(self, _id=None):
        tok = M.OAuthAccessToken.query.get(_id=bson.ObjectId(_id))
        if tok is None:
            flash('Invalid app ID', 'error')
            redirect('.')
        if tok.user_id != c.user._id:
            flash('Invalid app ID', 'error')
            redirect('.')
        tok.delete()
        flash('Application access revoked')
        redirect('.')

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

class OAuthController(BaseController):

    @with_trailing_slash
    @expose('jinja:allura:templates/oauth_applications.html')
    def index(self, **kw):
        require_authenticated()
        c.form = F.oauth_application_form
        return dict(apps=M.OAuthConsumerToken.for_user(c.user))

    @expose()
    @require_post()
    @validate(F.oauth_application_form, error_handler=index)
    def register(self, application_name=None, application_description=None, **kw):
        require_authenticated()
        M.OAuthConsumerToken(name=application_name, description=application_description)
        flash('OAuth Application registered')
        redirect('.')

    @expose()
    @require_post()
    def delete(self, id=None):
        require_authenticated()
        app = M.OAuthConsumerToken.query.get(_id=bson.ObjectId(id))
        if app is None:
            flash('Invalid app ID', 'error')
            redirect('.')
        if app.user_id != c.user._id:
            flash('Invalid app ID', 'error')
            redirect('.')
        app.delete()
        flash('Application deleted')
        redirect('.')
