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

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import
import os
import sys
import six.moves.urllib.request, six.moves.urllib.parse, six.moves.urllib.error
import six.moves.urllib.parse
from optparse import OptionParser
import json

from six.moves.configparser import ConfigParser, NoOptionError
import webbrowser
import oauth2 as oauth
from io import open
from six.moves import input


def main():
    op = OptionParser(usage='usage: %prog [options]',
                      description='Reads the wiki pages from one Allura wiki instance and uploads them to another Allura wiki instance.')
    op.add_option('-f', '--from-wiki', action='store', dest='from_wiki',
                  help='URL of wiki API to copy from like http://fromserver.com/rest/p/test/wiki/')
    op.add_option('-t', '--to-wiki', action='store', dest='to_wiki',
                  help='URL of wiki API to copy to like http://toserver.com/rest/p/test/wiki/')
    op.add_option('-D', '--debug', action='store_true',
                  dest='debug', default=False)
    (options, args) = op.parse_args(sys.argv[1:])

    base_url = options.to_wiki.split('/rest/')[0]
    oauth_client = make_oauth_client(base_url)

    wiki_data = six.moves.urllib.request.urlopen(options.from_wiki).read()
    wiki_json = json.loads(wiki_data)['pages']
    for p in wiki_json:
        from_url = options.from_wiki + six.moves.urllib.parse.quote(p)
        to_url = options.to_wiki + six.moves.urllib.parse.quote(p)
        try:
            page_data = six.moves.urllib.request.urlopen(from_url).read()
            page_json = json.loads(page_data)
            if options.debug:
                print(page_json['text'])
                break
            resp = oauth_client.request(
                to_url, 'POST', body=six.moves.urllib.parse.urlencode(dict(text=page_json['text'].encode('utf-8'))))
            if resp[0]['status'] == '200':
                print("Posted {0} to {1}".format(page_json['title'], to_url))
            else:
                print("Error posting {0} to {1}: {2} (project may not exist)".format(page_json['title'], to_url, resp[0]['status']))
                break
        except:
            print("Error processing " + p)
            raise


def make_oauth_client(base_url):
    """
    Build an oauth.Client with which callers can query Allura.
    """
    config_file = os.path.join(os.environ['HOME'], '.allurarc')
    cp = ConfigParser()
    cp.read(config_file)

    REQUEST_TOKEN_URL = base_url + '/rest/oauth/request_token'
    AUTHORIZE_URL = base_url + '/rest/oauth/authorize'
    ACCESS_TOKEN_URL = base_url + '/rest/oauth/access_token'
    oauth_key = option(cp, base_url, 'oauth_key',
                       'Forge API OAuth Key (%s/auth/oauth/): ' % base_url)
    oauth_secret = option(cp, base_url, 'oauth_secret',
                          'Forge API Oauth Secret: ')
    consumer = oauth.Consumer(oauth_key, oauth_secret)

    try:
        oauth_token = cp.get(base_url, 'oauth_token')
        oauth_token_secret = cp.get(base_url, 'oauth_token_secret')
    except NoOptionError:
        client = oauth.Client(consumer)
        resp, content = client.request(REQUEST_TOKEN_URL, 'GET')
        assert resp['status'] == '200', resp

        request_token = dict(six.moves.urllib.parse.parse_qsl(content))
        pin_url = "%s?oauth_token=%s" % (
            AUTHORIZE_URL, request_token['oauth_token'])
        if getattr(webbrowser.get(), 'name', '') == 'links':
            # sandboxes
            print(("Go to %s" % pin_url))
        else:
            webbrowser.open(pin_url)
        oauth_verifier = input('What is the PIN? ')

        token = oauth.Token(
            request_token['oauth_token'], request_token['oauth_token_secret'])
        token.set_verifier(oauth_verifier)
        client = oauth.Client(consumer, token)
        resp, content = client.request(ACCESS_TOKEN_URL, "GET")
        access_token = dict(six.moves.urllib.parse.parse_qsl(content))
        oauth_token = access_token['oauth_token']
        oauth_token_secret = access_token['oauth_token_secret']

        cp.set(base_url, 'oauth_token', oauth_token)
        cp.set(base_url, 'oauth_token_secret', oauth_token_secret)

    # save oauth token for later use
    cp.write(open(config_file, 'w'))
    print('Saving oauth tokens in {} for later re-use'.format(config_file))
    print()

    access_token = oauth.Token(oauth_token, oauth_token_secret)
    oauth_client = oauth.Client(consumer, access_token)
    return oauth_client


def option(cp, section, key, prompt=None):
    if not cp.has_section(section):
        cp.add_section(section)
    if cp.has_option(section, key):
        value = cp.get(section, key)
    else:
        value = input(prompt or ('%s: ' % key))
        cp.set(section, key, value)
    return value


if __name__ == '__main__':
    main()
