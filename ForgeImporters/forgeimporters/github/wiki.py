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

import git
from datetime import datetime
from tempfile import mkdtemp
from shutil import rmtree

from pylons import app_globals as g
from pylons import tmpl_context as c

from allura.lib import helpers as h
from forgeimporters.base import ToolImporter
from forgeimporters.github import GitHubProjectExtractor
from forgewiki import model as WM

import logging
log = logging.getLogger(__name__)

TARGET_APPS = []

try:
    from forgewiki.wiki_main import ForgeWikiApp
    TARGET_APPS.append(ForgeWikiApp)
except ImportError:
    pass


class GitHubWikiImporter(ToolImporter):
    target_app = TARGET_APPS
    source = 'GitHub'
    tool_label = 'Wiki'
    tool_description = 'Import your wiki from GitHub'

    def import_tool(self, project, user, project_name=None, mount_point=None, mount_label=None, user_name=None, **kw):
        """ Import a GitHub wiki into a new Wiki Allura tool.

        """
        project_name = "%s/%s" % (user_name, project_name)
        extractor = GitHubProjectExtractor(project_name)
        if not extractor.has_wiki():
            return

        app = project.install_app(
            "Wiki",
            mount_point=mount_point or 'wiki',
            mount_label=mount_label or 'Wiki')

        with h.push_config(c, app=app):
            for commit in self.get_wiki_pages(extractor.get_page_url('wiki_url')):
                for page_name, page in commit.iteritems():
                    wiki_page = WM.Page.upsert(page_name)
                    wiki_page.text = page[0]
                    wiki_page.mod_date = page[1]
                    wiki_page.timestamp = page[1]
                    wiki_page.viewable_by = ['all']
                    wiki_page.commit()

        g.post_event('project_updated')
        return app

    def get_blobs(self, commit):
        result = dict()
        for page in commit.tree.blobs:
            result[page.name.split('.')[0]] = [h.render_any_markup(page.name, h.really_unicode(page.data_stream.read())), datetime.utcfromtimestamp(commit.committed_date)]
        return result

    def get_wiki_pages(self, wiki_url):
        result = []
        wiki_path = mkdtemp()
        wiki = git.Repo.clone_from(wiki_url, to_path=wiki_path, bare=True)
        for commit in wiki.iter_commits():
            result.insert(0, self.get_blobs(commit))
        rmtree(wiki_path)
        return result
