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
import urllib
import urllib2
import json
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO
import logging

log = logging.getLogger(__name__)

class GitHubProjectExtractor(object):
    RE_REPO_TYPE = re.compile(r'(svn|hg|git)')
    PAGE_MAP = {
            'project_info': 'https://api.github.com/repos/%s',
        }


    def __init__(self, allura_project, gh_project_name, page):
        self.project = allura_project
        self.url = self.PAGE_MAP[page] % urllib.quote(gh_project_name)
        self.page = json.loads(urllib2.urlopen(self.url).read().decode('utf8'))

    def get_summmary(self):
        self.project.summary = self.page['description']
