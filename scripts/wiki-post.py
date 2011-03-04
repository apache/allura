#!/usr/bin/python

from sys import stdin, stdout
import hmac, hashlib
from datetime import datetime
import os
import urllib
from urllib2 import urlopen, HTTPError
from urlparse import urlparse, urljoin
import urllib
from optparse import OptionParser
from ConfigParser import ConfigParser

def smart_str(s, encoding='utf-8', strings_only=False, errors='strict'):
    """
    Returns a bytestring version of 's', encoded as specified in 'encoding'.

    If strings_only is True, don't convert (some) non-string-like objects.

    This function was borrowed from Django
    """
    if strings_only and isinstance(s, (types.NoneType, int)):
        return s
    elif not isinstance(s, basestring):
        try:
            return str(s)
        except UnicodeEncodeError:
            if isinstance(s, Exception):
                # An Exception subclass containing non-ASCII data that doesn't
                # know how to print itself properly. We shouldn't raise a
                # further exception.
                return ' '.join([smart_str(arg, encoding, strings_only,
                        errors) for arg in s])
            return unicode(s).encode(encoding, errors)
    elif isinstance(s, unicode):
        r = s.encode(encoding, errors)
        return r
    elif s and encoding != 'utf-8':
        return s.decode('utf-8', errors).encode(encoding, errors)
    else:
        return s

def generate_smart_str(params):
    for (key, value) in params:
        yield smart_str(key), smart_str(value)

def urlencode(params):
    """
    A version of Python's urllib.urlencode() function that can operate on
    unicode strings. The parameters are first case to UTF-8 encoded strings and
    then encoded as per normal.
    """
    return urllib.urlencode([i for i in generate_smart_str(params)])


class Signer(object):

    def __init__(self, secret_key, api_key):
        self.secret_key = secret_key
        self.api_key = api_key

    def __call__(self, path, params):
        if self.api_key is None:
            return params
        params.append(('api_key', self.api_key))
        params.append(('api_timestamp', datetime.utcnow().isoformat()))
        message = path + '?' + urlencode(sorted(params))
        digest = hmac.new(self.secret_key, message, hashlib.sha256).hexdigest()
        params.append(('api_signature', digest))
        return params

def main():
    usage = 'usage: %prog [options] [PageName [file]]'
    op = OptionParser(usage=usage)
    op.add_option('-c', '--config', metavar='CONFIG')
    op.add_option('-a', '--api-key', metavar='KEY')
    op.add_option('-s', '--secret-key', metavar='KEY')
    op.add_option('', '--anon', action='store_true')
    op.add_option('-u', '--url', metavar='URL')
    (options, args) = op.parse_args()

    pagename = None
    markdown = None
    method = 'GET'

    pagename_given = len(args) >= 1
    if pagename_given:
        pagename = args[0]

    filename_given = len(args) > 1
    if filename_given:
        method = 'PUT'
        f = open(args[1], 'r')
        markdown = f.read()

    config = ConfigParser()
    config.read([str(os.path.expanduser('~/.forge-api.ini')), str(options.config)])

    api_key = None
    secret_key = None
    if not options.anon:
        api_key = options.api_key or config.get('keys', 'api-key')
        secret_key = options.secret_key or config.get('keys', 'secret-key')

    url = options.url or config.get('wiki', 'url')
    if pagename_given:
        url = urljoin(url, urllib.quote(pagename))
    print url

    sign = Signer(secret_key, api_key)
    params = [('text', markdown)] if method=='PUT' else []
    params = sign(urlparse(url).path, params)
    try:
        if method=='PUT':
            result = urlopen(url, urlencode(params))
        else:
            result = urlopen(url+'?'+urlencode(params))
        stdout.write(result.read())
    except HTTPError, e:
        stdout.write(e.read())

if __name__ == '__main__':
    main()
