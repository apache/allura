#!/usr/bin/python

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

import types
from sys import stdout
import os
import urllib
from urllib2 import urlopen, HTTPError
from urlparse import urlparse, urljoin
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

    def __init__(self, token):
        self.token = token

    def __call__(self, path, params):
        if self.token is None:
            return params
        params.append(('token', self.token))
        return params


def main():
    usage = 'usage: %prog [options] [PageName [file]]'
    op = OptionParser(usage=usage, description='Use a markdown file to create/update a wiki page')
    op.add_option('-c', '--config', metavar='CONFIG')
    op.add_option('-t', '--token', metavar='TOKEN')
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
    config.read(
        [str(os.path.expanduser('~/.forge-api.ini')), str(options.config)])

    token = None
    if not options.anon:
        token = options.token or config.get('keys', 'token')

    url = options.url or config.get('wiki', 'url')
    if pagename_given:
        url = urljoin(url, urllib.quote(pagename))
    print url

    sign = Signer(token)
    params = [('text', markdown)] if method == 'PUT' else []
    params = sign(urlparse(url).path, params)
    try:
        if method == 'PUT':
            result = urlopen(url, urlencode(params))
        else:
            result = urlopen(url + '?' + urlencode(params))
        stdout.write(result.read())
    except HTTPError, e:
        stdout.write(e.read())

if __name__ == '__main__':
    main()
