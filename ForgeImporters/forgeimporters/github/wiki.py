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
    tool_option = {"history_github_wiki": "Import history"}
    # List of supported formats https://github.com/gollum/gollum/wiki#page-files
    supported_formats = [
            'asciidoc',
            'creole',
            'markdown',
            'mdown',
            'mkdn',
            'mkd',
            'md',
            'org',
            'pod',
            'rdoc',
            'rest.txt',
            'rst.txt',
            'rest',
            'rst',
            'textile',
            'mediawiki',
            'wiki'
    ]

    def import_tool(self, project, user, project_name=None, mount_point=None, mount_label=None, user_name=None,
                    tool_option=None, **kw):
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
        get_wiki_with_history = tool_option == 'history_github_wiki'
        with h.push_config(c, app=app):
            self.get_wiki_pages(extractor.get_page_url('wiki_url'), history=get_wiki_with_history)
        g.post_event('project_updated')
        return app

    def get_blobs_without_history(self, commit):
        for page in commit.tree.blobs:
            name, ext = page.name.split('.', 1)
            if ext not in self.supported_formats:
                log.info('Not a wiki page %s. Skipping.' % page.name)
                continue
            wiki_page = WM.Page.upsert(name)
            wiki_page.text = h.render_any_markup(page.name, h.really_unicode(page.data_stream.read()))
            wiki_page.timestamp = wiki_page.mod_date = datetime.utcfromtimestamp(commit.committed_date)
            wiki_page.viewable_by = ['all']
            wiki_page.commit()

    def get_blobs_with_history(self, commit):
        for page_name in commit.stats.files.keys():
            name, ext = page_name.split('.', 1)
            if ext not in self.supported_formats:
                log.info('Not a wiki page %s. Skipping.' % page_name)
                continue
            wiki_page = WM.Page.upsert(name)
            if page_name in commit.tree:
                wiki_page.text = h.render_any_markup(
                    page_name,
                    h.really_unicode(commit.tree[page_name].data_stream.read()))
                wiki_page.timestamp = wiki_page.mod_date = datetime.utcfromtimestamp(commit.committed_date)
                wiki_page.viewable_by = ['all']
            else:
                wiki_page.deleted = True
                suffix = " {dt.hour}:{dt.minute}:{dt.second} {dt.day}-{dt.month}-{dt.year}".format(dt=datetime.utcnow())
                wiki_page.title += suffix
            wiki_page.commit()

    def get_wiki_pages(self, wiki_url, history=None):
        wiki_path = mkdtemp()
        wiki = git.Repo.clone_from(wiki_url, to_path=wiki_path, bare=True)
        if not history:
            return self.get_blobs_without_history(wiki.heads.master.commit)

        commits = [commit for commit in wiki.iter_commits()]
        for commit in reversed(commits):
            self.get_blobs_with_history(commit)
        rmtree(wiki_path)
