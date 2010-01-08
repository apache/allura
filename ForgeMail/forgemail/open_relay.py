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
    if options.ssl:
        smtp_client = smtplib.SMTP_SSL(options.host, int(options.port))
    else:
        smtp_client = smtplib.SMTP(options.host, int(options.port))
    if options.tls:
        smtp_client.starttls()
    if options.login:
        username = raw_input('Username:')
        password = getpass('Password:')
        smtp_client.login(username, password)
    server = MailServer(('0.0.0.0', 8826), None,
                        smtp_client=smtp_client)
    asyncore.loop()

class MailServer(smtpd.SMTPServer):

    def __init__(self, *args, **kwargs):
        self._client = kwargs.pop('smtp_client')
        smtpd.SMTPServer.__init__(self, *args, **kwargs)

    def process_message(self, peer, mailfrom, rcpttos, data):
        self._client.sendmail(mailfrom, rcpttos, data)

if __name__ == '__main__':
    main()
