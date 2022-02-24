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
import six.moves.html_parser
import re

from tg import tmpl_context as c, app_globals as g, config
from bson import ObjectId
import markupsafe

from allura.lib import helpers as h
from allura.lib.decorators import task
from allura.lib import mail_util
from allura.lib import exceptions as exc
import six

log = logging.getLogger(__name__)

smtp_client = mail_util.SMTPClient()


def mail_meta_content(metalink):
    '''
    Helper function used to include a view action button in your email client
    https://developers.google.com/gmail/markup/reference/go-to-action#view_action

    :param metalink:  url to the page the action button links to
    '''

    return markupsafe.Markup("""\
    <div itemscope itemtype="http://schema.org/EmailMessage">
    <div itemprop="action" itemscope itemtype="http://schema.org/ViewAction">
      <link itemprop="url" href="%s"></link>
      <meta itemprop="name" content="View"></meta>
    </div>
    <meta itemprop="description" content="View"></meta>
    </div>""" % metalink)


@task
def route_email(
        peer, mailfrom, rcpttos, data):
    '''
    Route messages according to their destination:

    <topic>@<mount_point>.<subproj2>.<subproj1>.<project>.projects.domain.net
    gets sent to c.app.handle_message(topic, message)
    '''
    try:
        msg = mail_util.parse_message(data)
    except Exception:  # pragma no cover
        log.exception('Parse Error: (%r,%r,%r)', peer, mailfrom, rcpttos)
        return
    if mail_util.is_autoreply(msg):
        log.info('Skipping autoreply message: %s', msg['headers'])
        return
    mail_user = mail_util.identify_sender(peer, mailfrom, msg['headers'], msg)
    with h.push_config(c, user=mail_user):
        log.info('Received email from %s', c.user.username)
        # For each of the addrs, determine the project/app and route
        # appropriately
        for addr in rcpttos:
            try:
                userpart, project, app = mail_util.parse_address(addr)
                with h.push_config(c, project=project, app=app):
                    if not app.has_access(c.user, userpart):
                        log.info('Access denied for %s to mailbox %s',
                                 c.user, userpart)
                    elif not c.app.config.options.get('AllowEmailPosting', True):
                        log.info("Posting from email is not enabled")
                    else:
                        if msg['multipart']:
                            msg_hdrs = msg['headers']
                            for part in msg['parts']:
                                if part.get('content_type', '').startswith('multipart/'):
                                    continue
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
            except exc.MailError as e:
                log.error('Error routing email to %s: %s', addr, e)
            except Exception:
                log.exception('Error routing mail to %s', addr)


def create_multipart_msg(text, metalink=None):
    """
    Convert Markdown text to plaintext & HTML, combine into a multipart email Message
    :param text:
    :param metalink:
    :return:
    """

    def replace_html(matchobj):
        text_within_div = matchobj.group(1)
        text_within_div = text_within_div.replace('</p>', '\n')
        text_within_div = markupsafe._striptags_re.sub('', text_within_div)
        return text_within_div

    plain_text = text
    plain_text = re.sub(r'<div class="markdown_content">(.*)</div>',  # strip HTML from markdown generated blocks
                        replace_html,
                        plain_text,
                        flags=re.DOTALL,  # match newlines too
                        )
    plain_text = six.moves.html_parser.HTMLParser().unescape(plain_text)  # put literal HTML tags back into plaintext
    plain_msg = mail_util.encode_email_part(plain_text, 'plain')

    html_text = g.forge_markdown(email=True).convert(text)
    if metalink:
        html_text = html_text + mail_meta_content(metalink)
    html_msg = mail_util.encode_email_part(html_text, 'html')

    multi_msg = mail_util.make_multipart_message(plain_msg, html_msg)
    return multi_msg, plain_msg


@task
def sendmail(fromaddr, destinations, text, reply_to, subject,
             message_id, in_reply_to=None, sender=None, references=None, metalink=None):
    '''
    Send an email to the specified list of destinations with respect to the preferred email format specified by user.
    It is best for broadcast messages.

    :param fromaddr: ObjectId or str(ObjectId) of user, or email address str

    '''
    from allura import model as M
    addrs_plain = []
    addrs_multi = []
    if fromaddr is None:
        fromaddr = g.noreply
    elif not isinstance(fromaddr, str) or '@' not in fromaddr:
        log.warning('Looking up user with fromaddr: %s', fromaddr)
        user = M.User.query.get(_id=ObjectId(fromaddr), disabled=False, pending=False)
        if not user:
            log.warning('Cannot find user with ID: %s', fromaddr)
            fromaddr = g.noreply
        else:
            fromaddr = user.email_address_header()
    # Divide addresses based on preferred email formats
    for addr in destinations:
        if mail_util.isvalid(addr):
            addrs_plain.append(addr)
        else:
            try:
                user = M.User.query.get(_id=ObjectId(addr), disabled=False, pending=False)
                if not user:
                    log.warning('Cannot find user with ID: %s', addr)
                    continue
            except Exception:
                log.exception('Error looking up user with ID: %r' % addr)
                continue
            addr = user.email_address_header()
            if not addr and user.email_addresses:
                addr = user.email_addresses[0]
                log.warning(
                    'User %s has not set primary email address, using %s',
                    user._id, addr)
            if not addr:
                log.error(
                    "User %s (%s) has not set any email address, can't deliver",
                    user._id, user.username)
                continue
            if user.get_pref('email_format') == 'plain':
                addrs_plain.append(addr)
            else:
                addrs_multi.append(addr)

    multi_msg, plain_msg = create_multipart_msg(text, metalink)
    smtp_client.sendmail(
        addrs_multi, fromaddr, reply_to, subject, message_id,
        in_reply_to, multi_msg, sender=sender, references=references)
    smtp_client.sendmail(
        addrs_plain, fromaddr, reply_to, subject, message_id,
        in_reply_to, plain_msg, sender=sender, references=references)


@task
def sendsimplemail(
        fromaddr,
        toaddr,
        text,
        reply_to,
        subject,
        message_id,
        in_reply_to=None,
        sender=None,
        references=None,
        cc=None):
    '''
    Send a single mail to the specified address.
    It is best for single user notifications.

    :param fromaddr: ObjectId or str(ObjectId) of user, or email address str
    :param toaddr: ObjectId or str(ObjectId) of user, or email address str

    '''
    from allura import model as M
    if fromaddr is None:
        fromaddr = g.noreply
    elif not isinstance(fromaddr, str) or '@' not in fromaddr:
        log.warning('Looking up user with fromaddr: %s', fromaddr)
        user = M.User.query.get(_id=ObjectId(fromaddr), disabled=False, pending=False)
        if not user:
            log.warning('Cannot find user with ID: %s', fromaddr)
            fromaddr = g.noreply
        else:
            fromaddr = user.email_address_header()

    if not isinstance(toaddr, str) or '@' not in toaddr:
        log.warning('Looking up user with toaddr: %s', toaddr)
        user = M.User.query.get(_id=ObjectId(toaddr), disabled=False, pending=False)
        if not user:
            log.warning('Cannot find user with ID: %s', toaddr)
            toaddr = g.noreply
        else:
            toaddr = user.email_address_header()

    multi_msg, plain_msg = create_multipart_msg(text)
    smtp_client.sendmail(
        [toaddr], fromaddr, reply_to, subject, message_id,
        in_reply_to, multi_msg, sender=sender, references=references, cc=cc, to=toaddr)


def send_system_mail_to_user(user_or_emailaddr, subject, text):
    '''
    Sends a standard email from the Allura system itself, to a user.
    This is a helper function around sendsimplemail() that generates a new task

    :param user_or_emailaddr: an email address (str) or a User object
    :param subject: subject of the email
    :param text: text of the email (markdown)
    '''
    if isinstance(user_or_emailaddr, str):
        toaddr = user_or_emailaddr
    else:
        toaddr = user_or_emailaddr._id

    email = {
        'toaddr': toaddr,
        'fromaddr': '"{}" <{}>'.format(
            config['site_name'],
            config['forgemail.return_path']
        ),
        'sender': str(config['forgemail.return_path']),
        'reply_to': str(config['forgemail.return_path']),
        'message_id': h.gen_message_id(),
        'subject': subject,
        'text': text,
    }
    sendsimplemail.post(**email)
