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

import re
import logging
import json
import time
import requests
import six.moves.urllib.parse
import six.moves.urllib.request
import six.moves.urllib.error
from datetime import datetime

from tg import config, session, redirect, request, expose
from tg.decorators import without_trailing_slash
from tg import tmpl_context as c
from requests_oauthlib import OAuth2Session
from formencode import validators as fev

from forgeimporters import base
from urllib.parse import urlparse

log = logging.getLogger(__name__)


class GitHubURLValidator(fev.FancyValidator):
    regex = r'https?:\/\/github\.com'
    def _to_python(self, value, state):
        valid_url = urlparse(value.strip())
        if not bool(valid_url.scheme):
            raise fev.Invalid('Invalid URL', value, state)
        if not re.match(self.regex, value):
            raise fev.Invalid('Invalid Github URL', value, state)
        return value

class GitHubProjectNameValidator(fev.FancyValidator):
    not_empty = True
    messages = {
        'invalid': 'Valid symbols are: letters, numbers, dashes, '
                   'underscores and periods',
        'unavailable': 'This is not a valid Github project that can be used for import',
    }

    def _to_python(self, value, state=None):
        user_name = state.full_dict.get('user_name', '')
        user_name = state.full_dict.get('gh_user_name', user_name).strip()
        project_name = value.strip()
        full_project_name = f'{user_name}/{project_name}'
        if not re.match(r'^[a-zA-Z0-9-_.]+$', project_name):
            raise fev.Invalid(self.message('invalid', state), value, state)

        if not GitHubProjectExtractor(full_project_name, user=c.user).check_readable():
            raise fev.Invalid(self.message('unavailable', state), value, state)
        return project_name


class GitHubProjectExtractor(base.ProjectExtractor):
    PAGE_MAP = {
        'project_info': 'https://api.github.com/repos/{project_name}',
        'issues': 'https://api.github.com/repos/{project_name}/issues',
        'wiki_url': 'https://github.com/{project_name}.wiki',
    }
    POSSIBLE_STATES = ('open', 'closed')
    SUPPORTED_ISSUE_EVENTS = ('closed', 'reopened', 'assigned')
    NEXT_PAGE_URL_RE = re.compile(r'<([^>]*)>; rel="next"')

    def __init__(self, *args, **kw):
        self.token = None
        user = kw.pop('user', None)
        if user:
            self.token = user.get_tool_data('GitHubProjectImport', 'token')
        super().__init__(*args, **kw)

    def add_token(self, url):
        headers = {}
        if self.token:
            headers['Authorization'] = f'token {self.token}'
        return url, headers

    def wait_for_limit_reset(self, headers):
        reset = headers.get('X-RateLimit-Reset')
        limit = headers.get('X-RateLimit-Limit')
        reset = datetime.utcfromtimestamp(int(reset))
        now = datetime.utcnow()
        log.warn('Rate limit exceeded (%s requests/hour). '
                 'Sleeping until %s UTC' % (limit, reset))
        time.sleep((reset - now).total_seconds() + 2)

    def urlopen(self, url, headers=None, **kw):
        if headers is None:
            headers = {}
        try:
            url, auth_headers = self.add_token(url)
            # need to use unredirected_hdrs for Authorization for APIs that redirect to an AWS file asset which has
            # separate authentication added automatically
            resp = super().urlopen(url,
                                                               headers=headers, unredirected_hdrs=auth_headers, **kw)
        except six.moves.urllib.error.HTTPError as e:
            # GitHub will return 403 if rate limit exceeded.
            # We're checking for limit on every request below, but we still
            # can get 403 if other import task exceeds the limit before.
            if e.code == 403 and e.info().get('X-RateLimit-Remaining') == '0':
                self.wait_for_limit_reset(e.info())
                return self.urlopen(url, **kw)
            else:
                raise e
        remain = resp.info().get('X-RateLimit-Remaining')
        if remain and int(remain) == 0:
            self.wait_for_limit_reset(resp.info())
            return self.urlopen(url, **kw)
        return resp

    def check_readable(self):
        url, headers = self.add_token(self.get_page_url('project_info'))
        headers['User-Agent'] = 'Allura Data Importer (https://allura.apache.org/)'
        resp = requests.head(url, headers=headers, timeout=10)
        return resp.status_code == 200

    def get_next_page_url(self, link):
        if not link:
            return
        m = self.NEXT_PAGE_URL_RE.match(link)
        return m.group(1) if m else None

    def parse_page(self, page):
        # Look at link header to handle pagination
        link = page.info().get('Link')
        next_page_url = self.get_next_page_url(link)
        return json.loads(page.read().decode('utf8')), next_page_url

    def get_page(self, page_name_or_url, **kw):
        page = super().get_page(
            page_name_or_url, **kw)
        page, next_page_url = page
        while next_page_url:
            p = super().get_page(next_page_url, **kw)
            p, next_page_url = p
            page += p
        self.page = page
        return self.page

    def get_summary(self):
        return self.get_page('project_info').get('description')

    def get_homepage(self):
        return self.get_page('project_info').get('homepage')

    def get_repo_url(self):
        return self.get_page('project_info').get('clone_url')

    def iter_issues(self):
        # github api doesn't allow getting closed and opened tickets in one
        # query
        issues = []
        url = self.get_page_url('issues') + '?state={state}'
        for state in self.POSSIBLE_STATES:
            issue_list_url = url.format(
                state=state,
            )
            issues += self.get_page(issue_list_url)
        issues.sort(key=lambda x: x['number'])
        for issue in issues:
            yield (issue['number'], issue)

    def iter_comments(self, issue):
        comments_url = issue['comments_url']
        comments = self.get_page(comments_url)
        yield from comments

    def iter_events(self, issue):
        events_url = issue['events_url']
        events = self.get_page(events_url)
        for event in events:
            if event.get('event') in self.SUPPORTED_ISSUE_EVENTS:
                yield event

    def has_wiki(self):
        return self.get_page('project_info').get('has_wiki')

    def has_tracker(self):
        return self.get_page('project_info').get('has_issues')


def oauth_app_basic_auth(config):
    client_id = config['github_importer.client_id']
    secret = config['github_importer.client_secret']
    return requests.auth.HTTPBasicAuth(client_id, secret)


def valid_access_token(access_token, scopes_required=None):
    tok_details = access_token_details(access_token)
    if not tok_details.status_code == 200:
        return False
    if scopes_required and not all(scope_req in tok_details.json()['scopes']
                                   for scope_req in scopes_required):
        return False
    return True


def access_token_details(access_token):
    # https://developer.github.com/v3/apps/oauth_applications/#check-a-token
    client_id = config['github_importer.client_id']
    url = f'https://api.github.com/applications/{client_id}/token'
    return requests.post(url, auth=oauth_app_basic_auth(config), timeout=10, json=dict(
        access_token=access_token,
    ))


class GitHubOAuthMixin:
    '''
    Support for github oauth web application flow.  This is an "OAuth App" not a "GitHub App"
    '''

    def oauth_begin(self, scope=None):  # type: (list[str]) -> None
        if c.user.is_anonymous():
            log.info("User needs authorization before importing a project")
            return None
        client_id = config.get('github_importer.client_id')
        secret = config.get('github_importer.client_secret')
        if not client_id or not secret:
            log.warn('github_importer.* not set up in .ini file; cannot use OAuth for GitHub')
            return  # GitHub app is not configured
        access_token = c.user.get_tool_data('GitHubProjectImport', 'token')
        if access_token and valid_access_token(access_token, scopes_required=scope):
            return
        redirect_uri = request.url.rstrip('/') + '/oauth_callback'
        oauth = OAuth2Session(client_id, redirect_uri=redirect_uri, scope=scope)
        auth_url, state = oauth.authorization_url(
            'https://github.com/login/oauth/authorize')
        # Used in callback to prevent CSRF
        session['github.oauth.state'] = state
        session['github.oauth.redirect'] = request.url
        session.save()
        redirect(auth_url)

    @without_trailing_slash
    @expose()
    def oauth_callback(self, **kw):
        self.handle_oauth_callback()

    def handle_oauth_callback(self):
        client_id = config.get('github_importer.client_id')
        secret = config.get('github_importer.client_secret')
        if not client_id or not secret:
            return  # GitHub app is not configured
        oauth = OAuth2Session(
            client_id, state=session.get('github.oauth.state'))
        token = oauth.fetch_token(
            'https://github.com/login/oauth/access_token',
            client_secret=secret,
            authorization_response=request.url
        )
        c.user.set_tool_data('GitHubProjectImport',
                             token=token['access_token'])
        self.oauth_callback_complete()
        redirect(session.get('github.oauth.redirect', '/'))

    def oauth_callback_complete(self):
        """Subclasses can implement this to perform additional actions when
        token is retrieved"""
        pass

    def oauth_has_access(self, scope):
        if not scope:
            return False
        token = c.user.get_tool_data('GitHubProjectImport', 'token')
        if not token:
            return False
        r = access_token_details(token)
        if r.status_code == 404:
            return False
        scopes = r.json()['scopes']
        return scope in scopes
