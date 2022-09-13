<!--
    Licensed to the Apache Software Foundation (ASF) under one
    or more contributor license agreements.  See the NOTICE file
    distributed with this work for additional information
    regarding copyright ownership.  The ASF licenses this file
    to you under the Apache License, Version 2.0 (the
    "License"); you may not use this file except in compliance
    with the License.  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing,
    software distributed under the License is distributed on an
    "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
    KIND, either express or implied.  See the License for the
    specific language governing permissions and limitations
    under the License.
-->

# Basic API architecture

All url endpoints are prefixed with /rest/ and the path to the project and tool.  

For example, in order to access a wiki installed in the 'test' project with the mount point 'docs' the API endpoint would be /rest/p/test/docs.

The following tools have API support:

* Project
* Wiki
* Tracker
* Discussion
* Blog
* External Link
* Admin
    * Project Export
    * Installing a new Tool
    * Webhooks
* User Profiles

# Authenticating requests

In order to use the API for authenticated actions, you should use the OAuth account page to create a consumer key for your application.  Once you have a consumer key, you must have a site user (e.g. your own account, if you're writing a single script) authorize your application to act on his or her behalf.

You can also use your normal browser session as authentication for the API.  This is useful for manually testing API calls or for in-browser applications (such as extensions or user-scripts).  It is not recommended for programatic access, however, as it would require you to store your account username and password, and thus cannot be easily managed or revoked.

Without authentication, all API requests have the permissions of an anonymous visitor.  To view or change anything that requires a login, you must authenticate to the API using OAuth.  You must first register for an OAuth consumer token at <https://forge-allura.apache.org/auth/oauth/>.  Once you have registered, you will be be able to see your consumer key and consumer secret, or generate a bearer token, at <https://forge-allura.apache.org/auth/oauth/>.


### OAuth With Bearer Tokens

The easiest way to use the API with your own account is to use a bearer token.  Once you have generated a bearer token at <https://forge-allura.apache.org.net/auth/oauth/>, you just include it in the request to the API via the `access_token` URL parameter, `access_token` POST form field, or http header like `Authorization: Bearer MY_BEARER_TOKEN`.

Note, however, that to use bearer tokens, you *must* use HTTPS/SSL for the request.

Simple URL example to access a private ticket:

https://forge-allura.apache.org/rest/p/allura/tickets/35/?access_token=MY_BEARER_TOKEN

Python code example to create a new ticket:

    import requests
    from pprint import pprint
    
    BEARER_TOKEN = '<bearer token from oauth page>'
    
    r = requests.post('https://forge-allura.apache.org/rest/p/test-project/tickets/new', params={
            'access_token': BEARER_TOKEN,
            'ticket_form.summary': 'Test ticket',
            'ticket_form.description': 'This is a test ticket',
            'ticket_form.labels': 'test',
            'ticket_form.custom_fields._my_num': '7',  # custom field with label "My Num"
                                                       # must be created first
        })
    if r.status_code == 200:
        print('Ticket created at: %s' % r.url)
        pprint(r.json())
    else:
        print('Error [%s]:\n%s' % (r.status_code, r.text))



### OAuth 1.0 Application Authorization (Third-Party Apps)


If you want your application to be able to use the API on behalf of another user, that user must authorize your application to act on their behalf.  This is usually accomplished by obtaining a request token and directing the user authorize the request.  The following is an example of how one would authorize an application in Python using the requests_oauthlib library.  First, run `pip install requests_oauthlib`

    from requests_oauthlib import OAuth1Session
    import webbrowser

    CONSUMER_KEY = '<consumer key from registration>'
    CONSUMER_SECRET = '<consumer secret from registration>'
    REQUEST_TOKEN_URL = 'https://forge-allura.apache.org/rest/oauth/request_token'
    AUTHORIZE_URL = 'https://forge-allura.apache.org/rest/oauth/authorize'
    ACCESS_TOKEN_URL = 'https://forge-allura.apache.org/rest/oauth/access_token'
    
    oauth = OAuth1Session(CONSUMER_KEY, client_secret=CONSUMER_SECRET, callback_uri='oob')
    
    # Step 1: Get a request token. This is a temporary token that is used for 
    # having the user authorize an access token and to sign the request to obtain 
    # said access token.
    
    request_token = oauth.fetch_request_token(REQUEST_TOKEN_URL)
    
    # these are intermediate tokens and not needed later
    # print("Request Token:")
    # print("    - oauth_token        = %s" % request_token['oauth_token'])
    # print("    - oauth_token_secret = %s" % request_token['oauth_token_secret'])
    # print()
    
    # Step 2: Redirect to the provider. Since this is a CLI script we do not 
    # redirect. In a web application you would redirect the user to the URL
    # below, specifying the additional parameter oauth_callback=<your callback URL>.
    
    webbrowser.open(oauth.authorization_url(AUTHORIZE_URL, request_token['oauth_token']))
    
    # Since we didn't specify a callback, the user must now enter the PIN displayed in 
    # their browser.  If you had specified a callback URL, it would have been called with 
    # oauth_token and oauth_verifier parameters, used below in obtaining an access token.
    oauth_verifier = input('What is the PIN? ')
    
    # Step 3: Once the consumer has redirected the user back to the oauth_callback
    # URL you can request the access token the user has approved. You use the 
    # request token to sign this request. After this is done you throw away the
    # request token and use the access token returned. You should store this 
    # access token somewhere safe, like a database, for future use.
    access_token = oauth.fetch_access_token(ACCESS_TOKEN_URL, oauth_verifier)
    
    print("Access Token:")
    print("    - oauth_token        = %s" % access_token['oauth_token'])
    print("    - oauth_token_secret = %s" % access_token['oauth_token_secret'])
    print()
    print("You may now access protected resources using the access tokens above.") 
    print()


You can then use your access token with the REST API.  For instance script to create a wiki page might look like this:

    from requests_oauthlib import OAuth1Session
    
    PROJECT='test'
    
    CONSUMER_KEY='<consumer key from app registration>'
    CONSUMER_SECRET='<consumer secret from app registration>'
    
    ACCESS_KEY='<access key from previous script>'
    ACCESS_SECRET='<access secret from previous script>'
    
    URL_BASE='https://forge-allura.apache.org/rest/'
    
    oauth = OAuth1Session(CONSUMER_KEY, client_secret=CONSUMER_SECRET,
                          resource_owner_key=ACCESS_KEY, resource_owner_secret=ACCESS_SECRET)
    
    response = oauth.post(URL_BASE + 'p/' + PROJECT + '/wiki/TestPage',
                          data=dict(text='This is a test page'))
    response.raise_for_status()
    print("Done.  Response was:")
    print(response)


# Permission checks

The `has_access` API can be used to run permission checks. It is available on a neighborhood, project and tool level.

It is only available to users that have 'admin' permission for corresponding neighborhood/project/tool.  
It requires `user` and `perm` parameters and will return JSON dict with `result` key, which contains boolean value, indicating if given `user` has `perm` permission to the neighborhood/project/tool.


# DOAP (Description of a Project) API

[DOAP](http://en.wikipedia.org/wiki/DOAP) is an RDF/XML specification for "Description of a Project"

Project information is available in DOAP format with additional custom RDF fields at /rest/p/{project}?doap

This is separate from the normal JSON API at /rest/p/{project}