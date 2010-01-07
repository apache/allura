import smtpd
import asyncore
import email.feedparser
from pprint import pformat

import tg
import pylons
from paste.script import command

import pyforge.command
from pyforge.lib.helpers import find_project
from pyforge.command import base

M = None

class SMTPServerCommand(pyforge.command.Command):
    min_args=1
    max_args=1
    usage = 'NAME <ini file>'
    summary = 'Handle incoming emails, routing them to RabbitMQ'
    parser = command.Command.standard_parser(verbose=True)
    parser.add_option('-c', '--context', dest='context',
                      help=('The context of the message (path to the project'
                            ' and/or plugin'))

    def command(self):
        global M
        self.basic_setup()
        from pyforge import model
        M = model
        server = MailServer((tg.config.get('forgemail.host', '0.0.0.0'),
                             tg.config.get('forgemail.port', 8825)),
                            None)
        asyncore.loop()

class MailServer(smtpd.SMTPServer):

    def process_message(self, peer, mailfrom, rcpttos, data):
        '''Route messages according to their destination:

        <topic>@<mount_point>.<subproj2>.<subproj1>.<project>.projects.sourceforge.net
        goes to the audit with routing ID
        <plugin name>.<topic>
        '''
        base.log.info('Msg Received from %s for %s', mailfrom, rcpttos)
        base.log.info('%s', data)
        common_suffix = tg.config.get('forgemail.domain', '.sourceforge.net')
        parsed_message = parse_message(data)
        sending_user = identify_sender(peer, mailfrom, parsed_message)
        base.log.info('Sender: %s', sending_user)
        base.log.info('Message headers:\n%s', pformat(parsed_message['headers']))
        if parsed_message['multipart']:
            for part in parsed_message['parts']:
                base.log.info('Message part:\n%s', part['payload'])
        else:
                base.log.info('Message payload:\n%s', parsed_message['payload'])
        for addr in rcpttos:
            try:
                user, domain = addr.split('@')
                # remove common domain suffix
                if not domain.endswith(common_suffix):
                    base.log.warning(
                        'Unknown domain, dropping message: %s', domain)
                    continue
                domain = domain[:-len(common_suffix)]
                path = list(reversed(domain.split('.')))
                project, mount_point = find_project(path)
                if project is None:
                    base.log.warning('Unknown project at %s', domain)
                    continue
                if len(mount_point) != 1:
                    base.log.warning('Unknown plugin at %s', domain)
                    continue
                pylons.c.project = project
                pylons.c.app = app = project.app_instance(mount_point[0])
                topic = '%s.%s' % (app.config.plugin_name, user)
                pylons.g.publish('audit', topic, dict(parsed_message,
                                                      user_id=str(sending_user._id)),
                                 serializer='yaml')
            except:
                base.log.exception('Error handling mail to %s', addr)

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
    base.log.info('Trying ID sender for addr %s', email_address)
    # Dumb ID -- just look for email address claimed by a particular user
    addr = M.EmailAddress.query.get(_id=M.EmailAddress.canonical(email_address))
    if addr and addr.claimed_by_user_id:
        return addr.claimed_by_user()
    # TODO: look at the From: header, maybe?
    return None

