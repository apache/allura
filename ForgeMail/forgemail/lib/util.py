import logging
import smtplib
import email.feedparser
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText

import tg
from paste.deploy.converters import asbool, asint, aslist
from pylons import c

from pyforge.lib.helpers import push_config, find_project
from pyforge import model as M

from . import exc

log = logging.getLogger(__name__)

COMMON_SUFFIX = tg.config.get('forgemail.domain', '.sourceforge.net')

def parse_address(addr):
    userpart, domain = addr.split('@')
    # remove common domain suffix
    if not domain.endswith(COMMON_SUFFIX):
        raise exc.AddressException, 'Unknown domain: ' + domain
    domain = domain[:-len(COMMON_SUFFIX)]
    path = list(reversed(domain.split('.')))
    project, mount_point = find_project(path)
    if project is None:
        raise exc.AddressException, 'Unknown project: ' + domain
    if len(mount_point) != 1:
        raise exc.AddressException, 'Unknown plugin: ' + domain
    with push_config(c, project=project):
        app = project.app_instance(mount_point[0])
        if not app:
            raise exc.AddressException, 'Unknown plugin: ' + domain
        topic = '%s.%s' % (app.config.plugin_name, userpart)
    return topic, project, app
        
def parse_message(data):
    # Parse the email to its constituent parts
    parser = email.feedparser.FeedParser()
    parser.feed(data)
    msg = parser.close()
    # Extract relevant data
    result = {}
    result['multipart'] = multipart = msg.is_multipart()
    result['headers'] = dict(msg)
    if multipart:
        result['parts'] = [
            dict(headers=dict(subpart),
                 payload=subpart.get_payload())
            for subpart in msg.walk() ]
    else:
        result['payload'] = msg.get_payload()
    return result

def identify_sender(peer, email_address, msg):
    # Dumb ID -- just look for email address claimed by a particular user
    addr = M.EmailAddress.query.get(_id=M.EmailAddress.canonical(email_address))
    if addr and addr.claimed_by_user_id:
        return addr.claimed_by_user()
    # TODO: look at the From: header, maybe?
    return None

def encode_email_part(content, content_type):
    try:
        return MIMEText(content, content_type, 'iso-8859-1')
    except:
        return MIMEText(content, content_type, 'utf-8')

def make_multipart_message(*parts):
    msg = MIMEMultipart('related')
    msg.preamble = 'This is a multi-part message in MIME format.'
    alt = MIMEMultipart('alternative')
    msg.attach(alt)
    for part in parts:
        alt.attach(part)
    return msg

class SMTPClient(object):

    def __init__(self):
        self._client = None

    def sendmail(self, addrs, addrfrom, subject, message_id, in_reply_to, message):
        if not addrs: return
        message['To'] = 'undisclosed-recipients'
        message['From'] = addrfrom
        message['Subject'] = subject
        message['Message-ID'] = message_id
        if in_reply_to:
            message['In-Reply-To'] = in_reply_to
        content = message.as_string()
        try:
            self._client.sendmail(addrfrom, addrs, content)
        except:
            self._connect()
            self._client.sendmail(addrfrom, addrs, content)

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
