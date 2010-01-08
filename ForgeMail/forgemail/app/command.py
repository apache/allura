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
        base.log.info('Msg Received from %s for %s', mailfrom, rcpttos)
        pylons.g.publish('audit', 'forgemail.received_email',
                         dict(peer=peer, mailfrom=mailfrom,
                              rcpttos=rcpttos, data=data),
                         serializer='pickle')
