#!/usr/bin/env python
import smtpd
import smtplib
import asyncore
from getpass import getpass
from optparse import OptionParser

def main():
    parser = OptionParser()
    parser.add_option('--host', dest='host')
    parser.add_option('-p', '--port', dest='port', default=25)
    parser.add_option('-s', '--ssl', dest='ssl', action='store_true', default=False)
    parser.add_option('-t', '--tls', dest='tls', action='store_true', default=False)
    parser.add_option('-l', '--login', dest='login', action='store_true', default=False)
    (options, args) = parser.parse_args()
    if options.login:
        username = raw_input('Username:')
        password = getpass('Password:')
    else:
        username = password = None
    smtp_client = MailClient(options.host,
                             int(options.port),
                             options.ssl,
                             options.tls,
                             username, password)
    server = MailServer(('0.0.0.0', 8826), None,
                        smtp_client=smtp_client)
    asyncore.loop()

class MailClient(object):

    def __init__(self, host, port, ssl, tls, username, password):
        self.host, self.port, self.ssl, self.tls, self.username, self.password = \
            host, port, ssl, tls, username, password
        self._client = None
        self._connect()

    def sendmail(self, mailfrom, rcpttos, data):
        print 'Sending mail to %s' % rcpttos
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
