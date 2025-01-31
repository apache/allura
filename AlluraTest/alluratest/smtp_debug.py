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

import tg
from aiosmtpd.handlers import Debugging, Sink
from aiosmtpd.controller import Controller
from io import StringIO
from paste.deploy.converters import asint

class BetterDebuggingServer:
    
    def process_message(self,  server, session, envelope):
        stream = StringIO()
        handler = Debugging(stream)  # throws away the email
        hostname = tg.config.get('forgemail.host', '0.0.0.0')
        port = asint(tg.config.get('forgemail.port', 8825))
        controller = Controller(handler, hostname=hostname, port=port)
        controller.start()

    async def handle_DATA(self,  server, session, envelope):
        try:
            rcpttos = envelope.rcpt_tos
            print('TO: ' + ', '.join(rcpttos))
        except Exception as error:
            return f'500 Could not process your message. Error {error}'
        return '250 OK'