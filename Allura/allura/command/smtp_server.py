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

import faulthandler
import tg
from paste.script import command

import allura.tasks
from allura.command import base
from allura.command.base import EmptyClass, Command
from allura.lib import helpers as h
from paste.deploy.converters import asint
from aiosmtpd.controller import Controller
from tg.wsgiapp import RequestLocals
import time


class SMTPServerCommand(base.Command):
    min_args = 1
    max_args = 1
    usage = '<ini file>'
    summary = 'Handle incoming emails, routing them to taskd'
    parser = command.Command.standard_parser(verbose=True)
    parser.add_option('-c', '--context', dest='context',
                      help=('The context of the message (path to the project'
                            ' and/or tool'))
    
    def command(self):
        faulthandler.enable()
        self.basic_setup()
        handler = MailServer()
        hostname = tg.config.get('forgemail.host', '0.0.0.0')
        port = asint(tg.config.get('forgemail.port', 8825))
        controller = Controller(handler, hostname=hostname, port=port)
        controller.start()
        while True:
            time.sleep(100000)
            
        
class MailServer:
    async def handle_DATA(self, server, session, envelope):
        try:
            peer = session.peer
            mailfrom = envelope.mail_from
            rcpttos = envelope.rcpt_tos
            data = envelope.content
            base.log.info('Msg Received from %s for %s', mailfrom, rcpttos)
            base.log.info(' (%d bytes)', len(data))
            # pass the app_globals into the request context again because it's in a different thread
            tgl = RequestLocals()
            tgl.tmpl_context = EmptyClass()
            tgl.app_globals = tg.app_globals
            tg.request_local.context._push_object(tgl)
            task = allura.tasks.mail_tasks.route_email.post(peer=peer, mailfrom=mailfrom, rcpttos=rcpttos,
                                                            data=h.really_unicode(data))
            base.log.info(f'Msg passed along as task {task._id}')
        except Exception as error:
            base.log.exception(f'Error handling msg - {error}')
            return '500 Could not process your message'

        return '250 OK'

