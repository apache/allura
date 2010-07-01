#!/usr/bin/python

from sys import stdout
import hmac, hashlib
from datetime import datetime
import urllib
from urlparse import urlparse, urljoin
import urllib2
import json
from formencode import variabledecode

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
        params.append(('api_key', self.api_key))
        params.append(('api_timestamp', datetime.utcnow().isoformat()))
        message = path + '?' + urlencode(sorted(params))
        digest = hmac.new(self.secret_key, message, hashlib.sha256).hexdigest()
        params.append(('api_signature', digest))
        return params


class TicketIterator(object):

    def __init__(self, secret_key, api_key, url, max_ticket, min_ticket=1):
        self.sign = Signer(secret_key, api_key)
        self.cur_ticket_num = min_ticket
        self.max_ticket_num = max_ticket
        self.url = url

    def __iter__(self):
        return self

    def next(self):
        if self.cur_ticket_num > self.max_ticket_num:
            raise StopIteration
        url = urljoin(self.url, str(self.cur_ticket_num))+'/'
        self.cur_ticket_num += 1
        params = self.sign(urlparse(url).path, [])
        try:
            f = urllib2.urlopen(url+'?'+urlencode(params))
        except urllib2.HTTPError, e:
            if e.code == 404:
                raise StopIteration
            else:
                raise
        ticket = json.loads(f.read())['ticket'] or {}
        for bad_key in ('assigned_to_id', 'created_date', 'reported_by', 'reported_by_id', 'super_id', 'sub_ids', '_id'):
            if bad_key in ticket:
                del ticket[bad_key]
        ticket['labels'] = ''
        return ticket


class TicketPoster(object):

    def __init__(self, secret_key, api_key, url):
        self.sign = Signer(secret_key, api_key)
        self.url = urljoin(url, 'new')

    def __call__(self, ticket):
        ticket = variabledecode.variable_encode(ticket, add_repetitions=False)
        params = [('ticket_form', json.dumps(ticket))]
        params = self.sign(urlparse(self.url).path, params)
        try:
            f = urllib2.urlopen(self.url, urlencode(params))
        except urllib2.HTTPError, e:
            stdout.write(e.read())


def main():
    pw_mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
    pw_mgr.add_password(None, 'https://newforge.sf.geek.net/', '<REALM USER>', '<REALM PASSWORD>')
    auth_handler = urllib2.HTTPBasicAuthHandler(pw_mgr)
    opener = urllib2.build_opener(auth_handler)
    urllib2.install_opener(opener)

    newforge = TicketIterator(
        secret_key='<YOUR NEWFORGE SECRET KEY>',
        api_key='<YOUR NEWFORGE API KEY>',
        url='https://newforge.sf.geek.net/rest/p/forge/tickets/',
#        max_ticket=672,
        max_ticket=5,
        min_ticket=1)

    # testing with a demo project, update this URL to a new tracker in the forge project
    post_to_production = TicketPoster(
        secret_key='<YOUR SOURCEFORGE SECRET KEY>',
        api_key='<YOUR SOURCEFORGE API KEY>',
        url='https://sourceforge.net/rest/p/wolftest/newtix/')

    for ticket in newforge:
        post_to_production(ticket)


if __name__ == '__main__':
    main()
