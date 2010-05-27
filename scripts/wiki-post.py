#!/usr/bin/python

from sys import stdin, stdout
import hmac, hashlib
from datetime import datetime
import os
from urllib import urlencode
from urllib2 import urlopen
from urlparse import urlparse, urljoin
from optparse import OptionParser
from ConfigParser import ConfigParser

class Signer(object):

    def __init__(self, secret_key, api_key):
        self.secret_key = secret_key
        self.api_key = api_key

    def __call__(self, path, params):
        params.append(('api_key', self.api_key))
        params.append(('api_timestamp', datetime.utcnow().isoformat()))
        message = path + '?' + urlencode(sorted(params))
        digest = hmac.new(self.secret_key, message, hashlib.sha256).hexdigest()
        params.append(('api_signature', digest))
        return params

def main():
    usage = 'usage: %prog [options] PageName [file]'
    op = OptionParser(usage=usage)
    op.add_option('-c', '--config', metavar='CONFIG')
    op.add_option('-a', '--api-key', metavar='KEY')
    op.add_option('-s', '--secret-key', metavar='KEY')
    op.add_option('-u', '--url', metavar='URL')
    (options, args) = op.parse_args()

    page = args[0]
    f = open(args[1], 'r') if len(args)>=1 else stdin
    markdown = f.read()

    config = ConfigParser()
    config.read([str(os.path.expanduser('~/.forge-api.ini')), str(options.config)])

    api_key = options.api_key or config.get('keys', 'api-key')
    secret_key = options.secret_key or config.get('keys', 'secret-key')
    # print an error message if no keys are found

    url = urljoin(options.url or config.get('wiki', 'url'), page)

    sign = Signer(secret_key, api_key)
    params = sign(urlparse(url).path, [('text', markdown)])
    result = urlopen(url, urlencode(params))
    stdout.write(result.read())

if __name__ == '__main__':
    main()
