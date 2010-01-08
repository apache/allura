import logging

import tg
from pylons import c, g

from pyforge.lib.decorators import audit
from pyforge.lib.helpers import push_config

from forgemail.lib import util, exc

log = logging.getLogger(__name__)

common_suffix = tg.config.get('forgemail.domain', '.sourceforge.net')

@audit('forgemail.received_email')
def received_email(routing_key, data):
    '''Route messages according to their destination:

    <topic>@<mount_point>.<subproj2>.<subproj1>.<project>.projects.sourceforge.net
    goes to the audit with routing ID
    <plugin name>.<topic>
    '''
    return
    msg = util.parse_message(data['data'])
    user = util.identify_sender(data['peer'], data['mailfrom'], msg)
    log.info('Received email from %s', user)
    # For each of the addrs, determine the project/app and route appropriately
    for addr in data['rcpttos']:
        try:
            topic, project, app = util.parse_address(addr)
            with push_config(c, project=project, app=app):
                if not app.has_access(user, topic):
                    log.info('Access denied for %s to mailbox %s',
                             user, topic)
                else:
                    g.publish('audit', topic,
                              dict(msg, user_id=str(user._id)),
                              serializer='yaml')
        except exc.ForgeMailException, e:
            log.error('Error routing email to %s: %s', addr, e)
        except:
            log.exception('Error routing mail to %s', addr)


