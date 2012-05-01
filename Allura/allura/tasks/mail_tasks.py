import logging

from pylons import c, g
from bson import ObjectId

from allura.lib import helpers as h
from allura.lib.decorators import task
from allura.lib import mail_util
from allura.lib import exceptions as exc

log = logging.getLogger(__name__)

smtp_client = mail_util.SMTPClient()

@task
def route_email(
    peer, mailfrom, rcpttos, data):
    '''Route messages according to their destination:

    <topic>@<mount_point>.<subproj2>.<subproj1>.<project>.projects.sourceforge.net
    gets sent to c.app.handle_message(topic, message)
    '''
    try:
        msg = mail_util.parse_message(data)
    except: # pragma no cover
        log.exception('Parse Error: (%r,%r,%r)', peer, mailfrom, rcpttos)
        return
    mail_user = mail_util.identify_sender(peer, mailfrom, msg['headers'], msg)
    with h.push_config(c, user=mail_user):
        log.info('Received email from %s', c.user.username)
        # For each of the addrs, determine the project/app and route appropriately
        for addr in rcpttos:
            try:
                userpart, project, app = mail_util.parse_address(addr)
                with h.push_config(c, project=project, app=app):
                    if not app.has_access(c.user, userpart):
                        log.info('Access denied for %s to mailbox %s', c.user, userpart)
                    else:
                        if msg['multipart']:
                            msg_hdrs = msg['headers']
                            for part in msg['parts']:
                                if part.get('content_type', '').startswith('multipart/'): continue
                                msg = dict(
                                    headers=dict(msg_hdrs, **part['headers']),
                                    message_id=part['message_id'],
                                    in_reply_to=part['in_reply_to'],
                                    references=part['references'],
                                    filename=part['filename'],
                                    content_type=part['content_type'],
                                    payload=part['payload'])
                                c.app.handle_message(userpart, msg)
                        else:
                            c.app.handle_message(userpart, msg)
            except exc.MailError, e:
                log.error('Error routing email to %s: %s', addr, e)
            except:
                log.exception('Error routing mail to %s', addr)

@task
def sendmail(fromaddr, destinations, text, reply_to, subject,
             message_id, in_reply_to=None):
    from allura import model as M
    addrs_plain = []
    addrs_html = []
    addrs_multi = []
    if fromaddr is None:
        fromaddr = 'noreply@in.sf.net'
    elif '@' not in fromaddr:
        log.warning('Looking up user with fromaddr %s', fromaddr)
        user = M.User.query.get(_id=ObjectId(fromaddr))
        if not user:
            log.warning('Cannot find user with ID %s', fromaddr)
            fromaddr = 'noreply@in.sf.net'
        else:
            fromaddr = user.email_address_header()
    # Divide addresses based on preferred email formats
    for addr in destinations:
        if mail_util.isvalid(addr):
            addrs_plain.append(addr)
        else:
            try:
                user = M.User.query.get(_id=ObjectId(addr))
                if not user:
                    log.warning('Cannot find user with ID %s', addr)
                    continue
            except:
                log.exception('Error looking up user with ID %r' % addr)
                continue
            addr = user.email_address_header()
            if not addr and user.email_addresses:
                addr = user.email_addresses[0]
                log.warning('User %s has not set primary email address, using %s',
                            user._id, addr)
            if not addr:
                log.error("User %s (%s) has not set any email address, can't deliver",
                          user._id, user.username)
                continue
            if user.get_pref('email_format') == 'plain':
                addrs_plain.append(addr)
            elif user.get_pref('email_format') == 'html':
                addrs_html.append(addr)
            else:
                addrs_multi.append(addr)
    plain_msg = mail_util.encode_email_part(text, 'plain')
    html_text = g.forge_markdown(email=True).convert(text)
    html_msg = mail_util.encode_email_part(html_text, 'html')
    multi_msg = mail_util.make_multipart_message(plain_msg, html_msg)
    smtp_client.sendmail(
        addrs_multi, fromaddr, reply_to, subject, message_id,
        in_reply_to, multi_msg)
    smtp_client.sendmail(
        addrs_plain, fromaddr, reply_to, subject, message_id,
        in_reply_to, plain_msg)
    smtp_client.sendmail(
        addrs_html, fromaddr, reply_to, subject, message_id,
        in_reply_to, html_msg)

@task
def sendsimplemail(
    fromaddr,
    toaddr,
    text,
    reply_to,
    subject,
    message_id,
    in_reply_to=None):
    from allura import model as M
    if fromaddr is None:
        fromaddr = 'noreply@in.sf.net'
    elif '@' not in fromaddr:
        log.warning('Looking up user with fromaddr %s', fromaddr)
        user = M.User.query.get(_id=ObjectId(fromaddr))
        if not user:
            log.warning('Cannot find user with ID %s', fromaddr)
            fromaddr = 'noreply@in.sf.net'
        else:
            fromaddr = user.email_address_header()
    plain_msg = mail_util.encode_email_part(text, 'plain')
    html_text = g.forge_markdown(email=True).convert(text)
    html_msg = mail_util.encode_email_part(html_text, 'html')
    multi_msg = mail_util.make_multipart_message(plain_msg, html_msg)
    smtp_client.sendmail(
        [toaddr], fromaddr, reply_to, subject, message_id,
        in_reply_to, multi_msg)
