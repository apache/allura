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
            for page_name, page_text in self.get_wiki_pages(extractor.get_wiki_url()).iteritems():
                page = WM.Page.upsert(page_name)
                page.text = page_text
                page.viewable_by = ['all']

        g.post_event('project_updated')
        return app

    def get_wiki_pages(self, wiki_url):
        result = dict()
        wiki_pages = self.get_wiki_pages_form_git(wiki_url)
        for page_name, page_text in wiki_pages.iteritems():
            page_text = h.render_any_markup(page_name, h.really_unicode(page_text))
            result[page_name.split('.')[0]] = page_text
        return result

    def get_wiki_pages_form_git(self, wiki_url):
        result = dict()
        wiki_path = mkdtemp()
        wiki = git.Repo.clone_from(wiki_url, wiki_path)
        for page in wiki.heads.master.commit.tree.blobs:
            result[page.name] = page.data_stream.read()
        rmtree(wiki_path)
        return result
