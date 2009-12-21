import logging, string

from tg import expose, session, flash, redirect
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import c
from webob import exc

from pyforge import model as M
from pyforge.lib.oid_helper import verify_oid, process_oid

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

class AuthController(object):

    @expose('pyforge.templates.login')
    @with_trailing_slash
    def index(self, *args, **kwargs):
        return dict(oid_providers=OID_PROVIDERS)

    @expose('pyforge.templates.custom_login')
    def login_verify_oid(self, provider, username):
        if provider:
            oid_url = string.Template(provider).safe_substitute(
                username=username)
        else:
            oid_url = username
        return verify_oid(oid_url, failure_redirect='.',
                          return_to='login_process_oid',
                          title='OpenID Login',
                          prompt='Click below to continue')

    @expose()
    def login_process_oid(self, **kw):
        oid_obj = process_oid(failure_redirect='.')
        c.user = oid_obj.claimed_by_user()
        session['userid'] = c.user._id
        session.save()
        if not c.user.username:
            import pdb; pdb.set_trace()
            flash('Please choose a user name for SourceForge, %s.'
                  % c.user.display_name)
            redirect('setup_openid_user')
        flash('Welcome back, %s' % c.user.display_name)
        redirect('/')

    @expose('pyforge.templates.setup_openid_user')
    def setup_openid_user(self):
        return dict()

    @expose()
    def do_setup_openid_user(self, username=None, display_name=None):
        if M.User.query.get(username=username):
            flash('That username is already taken.  Please choose another.',
                  'error')
            redirect('setup_openid_user')
        c.user.update(
            username=username,
            display_name=display_name)
        c.user.register_project(username, 'users')
        flash('Your username has been set to %s.' % username)
        redirect('/')

    @expose('pyforge.templates.claim_openid')
    def claim_oid(self):
        return dict(oid_providers=OID_PROVIDERS)

    @expose('pyforge.templates.custom_login')
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
    def claim_process_oid(self, **kw):
        oid_obj = process_oid(failure_redirect='claim_oid')
        if c.user:
            c.user.claim_openid(oid_obj._id)
            flash('Claimed %s' % oid_obj._id)
        redirect('/')

    @expose()
    def logout(self):
        session['userid'] = None
        session.save()
        redirect('/')

    @expose()
    def do_login(self, username, password):
        user = M.User.query.get(username=username)
        if user is None:
            session['userid'] = None
            session.save()
            raise exc.HTTPUnauthorized()
        if not user.validate_password(password):
            session['userid'] = None
            session.save()
            raise exc.HTTPUnauthorized()
        session['userid'] = user._id
        session.save()
        flash('Welcome back, %s' % user.display_name)
        redirect('/')
