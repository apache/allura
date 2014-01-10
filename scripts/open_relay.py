#!/usr/bin/env python

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
import os
import smtpd
import smtplib
import asyncore
from ConfigParser import ConfigParser

log = logging.getLogger(__name__)


def main():
    cp = ConfigParser()
    log.info('Read config from: %s',
             cp.read([os.path.join(os.environ['HOME'], '.open_relay.ini')]))
    host = cp.get('open_relay', 'host')
    port = cp.getint('open_relay', 'port')
    ssl = cp.getboolean('open_relay', 'ssl')
    tls = cp.getboolean('open_relay', 'tls')
    username = cp.get('open_relay', 'username')
    password = cp.get('open_relay', 'password')
    smtp_client = MailClient(host,
                             port,
                             ssl, tls,
                             username, password)
    MailServer(('0.0.0.0', 8826), None,
               smtp_client=smtp_client)
    asyncore.loop()


class MailClient(object):

    def __init__(self, host, port, ssl, tls, username, password):
        self.host, self.port, self.ssl, self.tls, self.username, self.password = \
            host, port, ssl, tls, username, password
        self._client = None
        self._connect()

    def sendmail(self, mailfrom, rcpttos, data):
        if str(mailfrom) == 'None':
            mailfrom = rcpttos[0]
        log.info('Sending mail to %s' % rcpttos)
        log.info('Sending mail from %s' % mailfrom)
        try:
            self._client.sendmail(mailfrom, rcpttos, data)
        except:
            self._connect()
            self._client.sendmail(mailfrom, rcpttos, data)

    def _connect(self):
        if self.ssl:
            self._client = smtplib.SMTP_SSL(self.host, int(self.port))
        else:
            self._client = smtplib.SMTP(self.host, int(self.port))
        if self.tls:
            self._client.starttls()
        if self.username:
            self._client.login(self.username, self.password)


class MailServer(smtpd.SMTPServer):

    def __init__(self, *args, **kwargs):
        self._client = kwargs.pop('smtp_client')
        smtpd.SMTPServer.__init__(self, *args, **kwargs)

    def process_message(self, peer, mailfrom, rcpttos, data):
        self._client.sendmail(mailfrom, rcpttos, data)

if __name__ == '__main__':
    main()
