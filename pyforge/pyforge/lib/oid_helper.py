import logging

from pylons import g, request
from tg import flash, redirect, session
from openid.consumer import consumer

from pyforge import model as M

log = logging.getLogger(__name__)

def verify_oid(oid_url, failure_redirect=None, return_to=None,
                  **kw):
    '''Step 1 of OID verification -- redirect to provider site'''
    log.info('Trying to login via %s', oid_url)
    realm = 'http://localhost.localdomain:8080/'
    return_to = realm + 'auth/' + return_to
    oidconsumer = consumer.Consumer(g.oid_session(), g.oid_store)
    try:
        req = oidconsumer.begin(oid_url)
    except consumer.DiscoveryFailure, ex:
        log.exception('Error in openid login')
        flash(str(ex[0]), 'error')
        redirect(failure_redirect)
    if req is None: # pragma no cover
        flash('No openid services found for <code>%s</code>' % oid_url,
              'error')
        redirect(failure_redirect)
    if req.shouldSendRedirect():
        redirect_url = req.redirectURL(
            realm, return_to, False)
        log.info('Redirecting to %r', redirect_url)
        session.save()
        redirect(redirect_url)
    else:
        return dict(kw, form=req.formMarkup(realm, return_to=return_to))    

def process_oid(failure_redirect=None):
    oidconsumer = consumer.Consumer(g.oid_session(), g.oid_store)
    info = oidconsumer.complete(request.params, request.url)
    display_identifier = info.getDisplayIdentifier() or info.identity_url
    if info.status == consumer.FAILURE and display_identifier:
        # In the case of failure, if info is non-None, it is the
        # URL that we were verifying. We include it in the error
        # message to help the user figure out what happened.
        fmt = "Verification of %s failed: %s"
        flash(fmt % (display_identifier, info.message), 'error')
        redirect(failure_redirect)
    elif info.status == consumer.SUCCESS:
        # Success means that the transaction completed without
        # error. If info is None, it means that the user cancelled
        # the verification.
        css_class = 'alert'

        # This is a successful verification attempt. If this
        # was a real application, we would do our login,
        # comment posting, etc. here.
        fmt = "You have successfully verified %s as your identity."
        message = fmt % display_identifier
        if info.endpoint.canonicalID:
            # You should authorize i-name users by their canonicalID,
            # rather than their more human-friendly identifiers.  That
            # way their account with you is not compromised if their
            # i-name registration expires and is bought by someone else.
            message += ("  This is an i-name, and its persistent ID is %s"
                        % info.endpoint.canonicalID )
        flash(message, 'info')
    elif info.status == consumer.CANCEL:
        # cancelled
        message = 'Verification cancelled'
        flash(message, 'error')
        redirect(failure_redirect)
    elif info.status == consumer.SETUP_NEEDED:
        if info.setup_url:
            message = '<a href=%s>Setup needed</a>' % info.setup_url
        else:
            # This means auth didn't succeed, but you're welcome to try
            # non-immediate mode.
            message = 'Setup needed'
        flash(message, 'error')
        redirect(failure_redirect)
    else:
        # Either we don't understand the code or there is no
        # openid_url included with the error. Give a generic
        # failure message. The library should supply debug
        # information in a log.
        message = 'Verification failed.'
        flash(message, 'error')
        redirect(failure_redirect)
    session.save()
    oid_obj = M.OpenId.upsert(info.identity_url, display_identifier=display_identifier)
    return oid_obj
