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

import logging
import json

from forgeimporters import base

log = logging.getLogger(__name__)


class GitHubProjectExtractor(base.ProjectExtractor):
    PAGE_MAP = {
            'project_info': 'https://api.github.com/repos/{project}',
            'issues': 'https://api.github.com/repos/{project}/issues',
        }
    POSSIBLE_STATES = ('opened', 'closed')

    def parse_page(self, page):
        return json.loads(page.read().decode('utf8'))

    def __init__(self, allura_project, gh_project_name, page):
        self.project = allura_project
        self.gh_project_name = gh_project_name
        self.url = self.PAGE_MAP[page].format(
            project=urllib.quote(gh_project_name),
        )
        self.page = json.loads(urllib2.urlopen(self.url).read().decode('utf8'))

    def get_summary(self):
        return self.get_page('project_info').get('description')

    def get_homepage(self):
        return self.get_page('project_info').get('homepage')

    def get_repo_url(self):
        return self.get_page('project_info').get('clone_url')

    def iter_issues(self):
        # github api doesn't allow getting closed and opened tickets in one query
        issues = []
        self.url += '?state={state}'
        for state in self.POSSIBLE_STATES:
            issue_list_url = self.url.format(
                state=state,
            )
            issues += json.loads(urllib2.urlopen(issue_list_url).read().decode('utf8'))
        issues.sort(key=lambda x: x['number'])
        for issue in issues:
            yield (issue['number'], issue)
