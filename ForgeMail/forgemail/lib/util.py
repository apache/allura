import logging
import email.feedparser

import tg
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
