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
import urllib2
from datetime import datetime

from tg import config, session, redirect, request, expose
from tg.decorators import without_trailing_slash
from pylons import tmpl_context as c
from requests_oauthlib import OAuth2Session
import requests
from formencode import validators as fev

from forgeimporters import base

log = logging.getLogger(__name__)


class GitHubProjectNameValidator(fev.FancyValidator):
    not_empty = True
    messages = {
        'invalid': 'Valid symbols are: letters, numbers, dashes, '
                   'underscores and periods',
        'unavailable': 'This project is unavailable for import',
    }

    def _to_python(self, value, state=None):
        user_name = state.full_dict.get('user_name', '')
        user_name = state.full_dict.get('gh_user_name', user_name).strip()
        project_name = value.strip()
        full_project_name = '%s/%s' % (user_name, project_name)
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
        super(GitHubProjectExtractor, self).__init__(*args, **kw)

    def add_token(self, url):
        if self.token:
            glue = '&' if '?' in url else '?'
            url += glue + 'access_token=' + self.token
        return url

    def wait_for_limit_reset(self, headers):
        reset = headers.get('X-RateLimit-Reset')
        limit = headers.get('X-RateLimit-Limit')
        reset = datetime.utcfromtimestamp(int(reset))
        now = datetime.utcnow()
        log.warn('Rate limit exceeded (%s requests/hour). '
                 'Sleeping until %s UTC' % (limit, reset))
        time.sleep((reset - now).total_seconds())

    def urlopen(self, url, **kw):
        try:
            resp = super(GitHubProjectExtractor, self).urlopen(
                self.add_token(url), **kw)
        except urllib2.HTTPError as e:
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
        resp = requests.head(self.add_token(self.get_page_url('project_info')))
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
        page = super(GitHubProjectExtractor, self).get_page(
            page_name_or_url, **kw)
        page, next_page_url = page
        while next_page_url:
            p = super(GitHubProjectExtractor,
                      self).get_page(next_page_url, **kw)
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
        for comment in comments:
            yield comment

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


class GitHubOAuthMixin(object):

    '''Support for github oauth web application flow.'''

    def oauth_begin(self, scope=None):
        client_id = config.get('github_importer.client_id')
        secret = config.get('github_importer.client_secret')
        if not client_id or not secret:
            return  # GitHub app is not configured
        if c.user.get_tool_data('GitHubProjectImport', 'token'):
            return  # token already exists, nothing to do
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
        url = 'https://api.github.com/?access_token={}'.format(token)
        r = requests.head(url)
        scopes = r.headers.get('X-OAuth-Scopes', '')
        scopes = [s.strip() for s in scopes.split(',')]
        return scope in scopes
