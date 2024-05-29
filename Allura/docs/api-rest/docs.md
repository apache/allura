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

You can also use your normal browser session as authentication for the API.  This is useful for manually testing API calls or for in-browser applications (such as extensions or user-scripts).  It is not recommended for programmatic access, however, as it would require you to store your account username and password, and thus cannot be easily managed or revoked.

Without authentication, all API requests have the permissions of an anonymous visitor.  To view or change anything that requires a login, you must authenticate to the API using OAuth.  You must first register for an OAuth consumer token at <https://forge-allura.apache.org/auth/oauth/>.  Once you have registered, you will be be able to see your consumer key and consumer secret, or generate a bearer token, at <https://forge-allura.apache.org/auth/oauth/>.


### OAuth With Bearer Tokens

The easiest way to use the API with your own account is to use a bearer token.  Once you have generated a bearer token at <https://forge-allura.apache.org.net/auth/oauth/>, you just include it in the request to the API via a http header like `Authorization: Bearer MY_BEARER_TOKEN`.

Simple URL example to access a private ticket:

curl -H 'Authorization: Bearer MY_BEARER_TOKEN' https://forge-allura.apache.org/rest/p/allura/tickets/35/

Python code example to create a new ticket:

    import requests
    from pprint import pprint

    BEARER_TOKEN = '<bearer token from oauth page>'

    r = requests.post('https://forge-allura.apache.org/rest/p/test-project/tickets/new',
          headers={'Authorization': f'Bearer {BEARER_TOKEN}'}
          params={
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

### OAuth2 Authorization (Third-Party Apps)

Another option for authorizing your apps is to use the OAuth2 workflow. This is accomplished by authorizing the application which generates an `authorization_code` that can be later exchanged for an `access_token`

The following example demonstrates the authorization workflow and how to generate an access token to authenticate your apps

    from requests_oauthlib import OAuth2Session

    # Set up your client credentials
    client_id = 'YOUR_CLIENT_ID'
    client_secret = 'YOUR_CLIENT_SECRET'
    authorization_base_url = 'https://forge-allura.apache.org/auth/oauth2/authorize'
    access_token_url = 'https://forge-allura.apache.org/rest/oauth2/token'
    redirect_uri = 'https://forge-allura.apache.org/page'  # Your registered redirect URI

    # Create an OAuth2 session
    oauth2 = OAuth2Session(client_id, redirect_uri=redirect_uri)

    # Step 1: Prompt the user to navigate to the authorization URL
    authorization_url, state = oauth2.authorization_url(authorization_base_url)

    print('Please go to this URL to authorize the app:', authorization_url)

    # Step 2: Obtain the authorization code (you can find it in the 'code' URL parameter)
    # In real use cases, you might implement a small web server to capture this
    authorization_code = input('Paste authorization code here: ')

    # Step 3: Exchange the authorization code for an access token
    token = oauth2.fetch_token(access_token_url,
                            code=authorization_code,
                            client_secret=client_secret,
                            include_client_id=True)

    # Print the access and refresh tokens for verification (or use it to request user data)
    # If your access token expires, you can request a new one using the refresh token
    print(f"Access Token: {token.get('access_token')}")
    print(f"Refresh Token: {token.get('refresh_token')}")

    # Step 4: Use the access token to make authenticated requests
    response = oauth2.get('https://forge-allura.apache.org/user')
    print('User data:', response.json())

### Refreshing Access Tokens

A new access token can be requested once it expires. The following example demonstrates how can the refresh token obtained in the previous code sample be used to generate a new access token:

    from requests_oauthlib import OAuth2Session

    # Set up your client credentials
    client_id = 'YOUR_CLIENT_ID'
    client_secret = 'YOUR_CLIENT_SECRET'
    refresh_token = 'YOUR_REFRESH_TOKEN'
    access_token = 'YOUR_ACCESS_TOKEN'
    access_token_url = 'https://forge-allura.apache.org/rest/oauth2/token'

    # Step 1: Create an OAuth2 session by also passing token information
    token = dict(access_token=access_token, token_type='Bearer', refresh_token=refresh_token)
    oauth2 = OAuth2Session(client_id=client_id, token=token)

    # Step 2: Request for a new token
    extra = dict(client_id=client_id, client_secret=client_secret)
    refreshed_token = oauth2.refresh_token(access_token_url, **extra)

    # You can inspect the response object to get the new access and refresh tokens
    print(f"Access Token: {token.get('access_token')}")
    print(f"Refresh Token: {token.get('refresh_token')}")

### PKCE support

PKCE (Proof Key for Code Exchange) is an extension to the authorization code flow to prevent CSRF and authorization code injection attacks. It mitigates the risk of the authorization code being intercepted by a malicious entity during the exchange from the authorization endpoint to the token endpoint.

To make use of this security extension, you must generate a string known as a "code verifier", which is a random string using the characters A-Z, a-z, 0-9 and the special characters -._~ and it should be between 43 and 128 characters long.

Once the string has been created, perform a SHA256 hash on it and encode the resulting value as a Base-

You can use the following example to generate a valid code verifier and code challenge:

    import hashlib
    import base64
    import os


    # Generate a code verifier (random string)
    def generate_code_verifier(length=64):
        return base64.urlsafe_b64encode(
          os.urandom(length)).decode('utf-8').rstrip('=')


    # Generate a code challenge (SHA-256)
    def generate_code_challenge(verifier):
        digest = hashlib.sha256(verifier.encode('utf-8')).digest()
        return base64.urlsafe_b64encode(digest).decode('utf-8').rstrip('=')


    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)

    # The code challenge should be sent in the initial authorization request.
    print("Code Verifier:", code_verifier)
    print("Code Challenge:", code_challenge)

Having generated the codes, you would need to send the code challenge along with the challenge method (in this case S256) as part of the query string in the authorization url, for example:

    https://forge-allura.apache.org/auth/oauth2/authorize?client_id=8dca182d3e6fe0cb76b8&response_type=code&code_challenge=G6wIRjEZlvhLsVS0exbID3o4ppUBsjxUBNtRVL8StXo&code_challenge_method=S256


Afterwards, when you request an access token, you must provide the code verifier that derived the code challenge as part of the request's body, otherwise the token request validation will fail:

    POST https://forge-allura.apache.org/rest/oauth2/token

    {
        "client_id": "8dca182d3e6fe0cb76b8",
        "client_secret": "1c6a2d99db80223590dd12cc32dfdb8a0cc2e9a38620e05c16076b2872110688b9c1b17db63bb7c3",
        "code": "Gvw53xmSBFZYBy0xdawm0qSX0cqhHs",
        "code_verifier": "aEyhTs4BfWjZ7g5HT0o7Hu24p6Qw6TxotdX8_G20NN9J1lXIfSnNr3b6jhOUZe5ZWkP5ADCEzlWABUHSPXslgQ",
        "grant_type": "authorization_code"
    }



# Permission checks

The `has_access` API can be used to run permission checks. It is available on a neighborhood, project and tool level.

It is only available to users that have 'admin' permission for corresponding neighborhood/project/tool.
It requires `user` and `perm` parameters and will return JSON dict with `result` key, which contains boolean value, indicating if given `user` has `perm` permission to the neighborhood/project/tool.


# DOAP (Description of a Project) API

[DOAP](http://en.wikipedia.org/wiki/DOAP) is an RDF/XML specification for "Description of a Project"

Project information is available in DOAP format with additional custom RDF fields at /rest/p/{project}?doap

This is separate from the normal JSON API at /rest/p/{project}
