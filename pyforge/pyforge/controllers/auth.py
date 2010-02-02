import logging, string
from pprint import pformat

from tg import expose, session, flash, redirect
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import c, request
from webob import exc

from pyforge import model as M
from pyforge.lib.oid_helper import verify_oid, process_oid
from pyforge.lib.security import require_authenticated
from pyforge.lib.helpers import vardec

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

    def __init__(self):
        self.prefs = PreferencesController()

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
            flash('Please choose a user name for SourceForge, %s.'
                  % c.user.display_name)
            redirect('setup_openid_user')
        flash('Welcome back, %s' % c.user.display_name)
        redirect('/')

    @expose('pyforge.templates.setup_openid_user')
    def setup_openid_user(self):
        return dict()

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
    def do_setup_openid_user(self, username=None, display_name=None):
        if M.User.query.get(username=username) and username != c.user.username:
            flash('That username is already taken.  Please choose another.',
                  'error')
            redirect('setup_openid_user')
        c.user.username = username
        c.user.display_name = display_name
        n = M.Neighborhood.query.get(name='Users')
        n.register_project('users/' + username)
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

class PreferencesController(object):

    @expose('pyforge.templates.user_preferences')
    def index(self):
        require_authenticated()
        return dict()

    @vardec
    @expose()
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
        c.user.display_name = display_name
        for i, (old_a, data) in enumerate(zip(c.user.email_addresses, addr or [])):
            obj = c.user.address_object(old_a)
            if data.get('delete') or not obj:
                del c.user.email_addresses[i]
                if obj: obj.delete()
        c.user.preferences.email_address = primary_addr
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
            c.user.preferences[k] = v
        redirect('.')
        
