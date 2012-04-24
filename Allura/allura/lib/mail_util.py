import re
import logging
import smtplib
import email.feedparser
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
from email import header

import tg
from paste.deploy.converters import asbool, asint
from formencode import validators as fev
from pylons import c

from allura.lib.utils import ConfigProxy
from allura.lib import exceptions as exc
from allura.lib import helpers as h

log = logging.getLogger(__name__)

RE_MESSAGE_ID = re.compile(r'<(.*)>')
config = ConfigProxy(
    common_suffix='forgemail.domain',
    return_path='forgemail.return_path')
EMAIL_VALIDATOR=fev.Email(not_empty=True)

def Header(text, *more_text):
    '''Helper to make sure we encode headers properly'''
    if isinstance(text, header.Header):
        return text
    # email.header.Header handles str vs unicode differently
    # see http://docs.python.org/library/email.header.html#email.header.Header.append
    if type(text) != unicode:
        raise TypeError('This must be unicode: %r' % text)
    head = header.Header(text)
    for m in more_text:
        if type(m) != unicode:
            raise TypeError('This must be unicode: %r' % text)
        head.append(m)
    return head

def AddrHeader(fromaddr):
    '''Accepts any of:
        Header() instance
        foo@bar.com
        "Foo Bar" <foo@bar.com>
    '''
    if isinstance(fromaddr, basestring) and ' <' in fromaddr:
        name, addr = fromaddr.rsplit(' <', 1)
        addr = '<' + addr # restore the char we just split off
        addrheader = Header(name, addr)
        if str(addrheader).startswith('=?'): # encoding escape chars
            # then quoting the name is no longer necessary
            name = name.strip('"')
            addrheader = Header(name, addr)
    else:
        addrheader = Header(fromaddr)
    return addrheader


def parse_address(addr):
    userpart, domain = addr.split('@')
    # remove common domain suffix
    if not domain.endswith(config.common_suffix):
        raise exc.AddressException, 'Unknown domain: ' + domain
    domain = domain[:-len(config.common_suffix)]
    path = '/'.join(reversed(domain.split('.')))
    project, mount_point = h.find_project('/' + path)
    if project is None:
        raise exc.AddressException, 'Unknown project: ' + domain
    if len(mount_point) != 1:
        raise exc.AddressException, 'Unknown tool: ' + domain
    with h.push_config(c, project=project):
        app = project.app_instance(mount_point[0])
        if not app:
            raise exc.AddressException, 'Unknown tool: ' + domain
    return userpart, project, app

def parse_message(data):
    # Parse the email to its constituent parts
    parser = email.feedparser.FeedParser()
    parser.feed(data)
    msg = parser.close()
    # Extract relevant data
    result = {}
    result['multipart'] = multipart = msg.is_multipart()
    result['headers'] = dict(msg)
    result['message_id'] = _parse_message_id(msg.get('Message-ID'))
    result['in_reply_to'] = _parse_message_id(msg.get('In-Reply-To'))
    result['references'] = _parse_message_id(msg.get('References'))
    if result['message_id'] == []:
        result['message_id'] = h.gen_message_id()
    else:
        result['message_id'] = result['message_id'][0]
    if multipart:
        result['parts'] = []
        for part in msg.walk():
            dpart = dict(
                headers=dict(part),
                message_id=result['message_id'],
                in_reply_to=result['in_reply_to'],
                references=result['references'],
                content_type=part.get_content_type(),
                filename=part.get_filename(None),
                payload=part.get_payload(decode=True))
            charset = part.get_content_charset()
            if charset:
                dpart['payload'] = dpart['payload'].decode(charset)
            result['parts'].append(dpart)
    else:
        result['payload'] = msg.get_payload(decode=True)
        charset = msg.get_content_charset()
        if charset:
            result['payload'] = result['payload'].decode(charset)
    return result

def identify_sender(peer, email_address, headers, msg):
    from allura import model as M
    # Dumb ID -- just look for email address claimed by a particular user
    addr = M.EmailAddress.query.get(_id=M.EmailAddress.canonical(email_address))
    if addr and addr.claimed_by_user_id:
        return addr.claimed_by_user()
    addr = M.EmailAddress.query.get(_id=M.EmailAddress.canonical(headers.get('From', '')))
    if addr and addr.claimed_by_user_id:
        return addr.claimed_by_user()
    return M.User.anonymous()

def encode_email_part(content, content_type):
    try:
        return MIMEText(content.encode('ascii'), content_type, 'ascii')
    except:
        return MIMEText(content.encode('utf-8'), content_type, 'utf-8')

def make_multipart_message(*parts):
    msg = MIMEMultipart('related')
    msg.preamble = 'This is a multi-part message in MIME format.'
    alt = MIMEMultipart('alternative')
    msg.attach(alt)
    for part in parts:
        alt.attach(part)
    return msg

def _parse_message_id(msgid):
    if msgid is None: return []
    return [ mo.group(1)
             for mo in RE_MESSAGE_ID.finditer(msgid) ]

def _parse_smtp_addr(addr):
    addr = str(addr)
    addrs = _parse_message_id(addr)
    if addrs and addrs[0]: return addrs[0]
    if '@' in addr: return addr
    return 'noreply@in.sf.net'

def isvalid(addr):
    '''return True if addr is a (possibly) valid email address, false
    otherwise'''
    try:
        EMAIL_VALIDATOR.to_python(addr, None)
        return True
    except fev.Invalid:
        return False

class SMTPClient(object):

    def __init__(self):
        self._client = None

    def sendmail(self, addrs, fromaddr, reply_to, subject, message_id, in_reply_to, message):
        if not addrs: return
        # We send one message with multiple envelope recipients, so use a generic To: addr
        # It might be nice to refactor to send one message per recipient, and use the actual To: addr
        message['To'] = Header(reply_to)
        message['From'] = AddrHeader(fromaddr)
        message['Reply-To'] = Header(reply_to)
        message['Subject'] = Header(subject)
        message['Message-ID'] = Header('<' + message_id + u'>')
        if in_reply_to:
            if not isinstance(in_reply_to, basestring):
                raise TypeError('Only strings are supported now, not lists')
            message['In-Reply-To'] = Header(u'<%s>' % in_reply_to)
        content = message.as_string()
        smtp_addrs = map(_parse_smtp_addr, addrs)
        smtp_addrs = [ a for a in smtp_addrs if isvalid(a) ]
        if not smtp_addrs:
            log.warning('No valid addrs in %s, so not sending mail',
                        map(unicode, addrs))
            return
        try:
            self._client.sendmail(
                config.return_path,
                smtp_addrs,
                content)
        except:
            self._connect()
            self._client.sendmail(
                config.return_path,
                smtp_addrs,
                content)

    def _connect(self):
        if asbool(tg.config.get('smtp_ssl', False)):
            smtp_client = smtplib.SMTP_SSL(
                tg.config.get('smtp_server', 'localhost'),
                asint(tg.config.get('smtp_port', 25)))
        else:
            smtp_client = smtplib.SMTP(
                tg.config.get('smtp_server', 'localhost'),
                asint(tg.config.get('smtp_port', 465)))
        if tg.config.get('smtp_user', None):
            smtp_client.login(tg.config['smtp_user'], tg.config['smtp_password'])
        if asbool(tg.config.get('smtp_tls', False)):
            smtp_client.starttls()
        self._client = smtp_client
