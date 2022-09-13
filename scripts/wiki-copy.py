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

import os
import sys
from optparse import OptionParser
from configparser import ConfigParser, NoOptionError
import webbrowser

import requests
from requests_oauthlib import OAuth1Session


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

    wiki_json = requests.get(options.from_wiki).json()['pages']
    for p in wiki_json:
        from_url = options.from_wiki.rstrip('/') + '/' + p
        to_url = options.to_wiki.rstrip('/') + '/' + p
        try:
            page_json = requests.get(from_url).json()
            if options.debug:
                print(page_json['text'])
                break
            resp = oauth_client.post(to_url, data=dict(text=page_json['text']))
            if resp.status_code == 200:
                print("Posted {} to {}".format(page_json['title'], to_url))
            else:
                print("Error posting {} to {}: {} (project may not exist)".format(page_json['title'], to_url, resp.status_code))
                break
        except Exception:
            print("Error processing " + p)
            raise


def make_oauth_client(base_url) -> requests.Session:
    """
    Build an oauth client with which callers can query Allura.
    """
    config_file = os.path.join(os.environ['HOME'], '.allurarc')
    cp = ConfigParser()
    cp.read(config_file)

    REQUEST_TOKEN_URL = base_url + '/rest/oauth/request_token'
    AUTHORIZE_URL = base_url + '/rest/oauth/authorize'
    ACCESS_TOKEN_URL = base_url + '/rest/oauth/access_token'
    oauth_key = option(cp, base_url, 'oauth_key',
                       'Forge API OAuth Consumer Key (%s/auth/oauth/): ' % base_url)
    oauth_secret = option(cp, base_url, 'oauth_secret',
                          'Forge API Oauth Consumer Secret: ')

    try:
        oauth_token = cp.get(base_url, 'oauth_token')
        oauth_token_secret = cp.get(base_url, 'oauth_token_secret')
    except NoOptionError:
        oauthSess = OAuth1Session(oauth_key, client_secret=oauth_secret, callback_uri='oob')
        request_token = oauthSess.fetch_request_token(REQUEST_TOKEN_URL)
        pin_url = oauthSess.authorization_url(AUTHORIZE_URL, request_token['oauth_token'])
        if isinstance(webbrowser.get(), webbrowser.GenericBrowser):
            print("Go to %s" % pin_url)
        else:
            webbrowser.open(pin_url)
        oauth_verifier = input('What is the PIN? ')
        access_token = oauthSess.fetch_access_token(ACCESS_TOKEN_URL, oauth_verifier)
        oauth_token = access_token['oauth_token']
        oauth_token_secret = access_token['oauth_token_secret']

        cp.set(base_url, 'oauth_token', oauth_token)
        cp.set(base_url, 'oauth_token_secret', oauth_token_secret)
        # save oauth token for later use
        cp.write(open(config_file, 'w'))
        print(f'Saving oauth tokens in {config_file} for later re-use')
        print()

    else:
        oauthSess = OAuth1Session(oauth_key, client_secret=oauth_secret,
                                  resource_owner_key=oauth_token, resource_owner_secret=oauth_token_secret)

    return oauthSess


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
