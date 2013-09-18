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
from datetime import datetime
from tempfile import mkdtemp
from shutil import rmtree

import git
from pylons import app_globals as g
from pylons import tmpl_context as c
from ming.orm import ThreadLocalORMSession
from formencode import validators as fev
from tg import (
        expose,
        validate,
        flash,
        redirect,
        )
from tg.decorators import (
        with_trailing_slash,
        without_trailing_slash,
        )

from allura.controllers import BaseController
from allura.lib import helpers as h
from allura.lib.decorators import (
        require_post,
        task,
        )
from allura import model as M
from forgeimporters.base import (
        ToolImporter,
        ToolImportForm,
        ImportErrorHandler,
        )
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


@task(notifications_disabled=True)
def import_tool(**kw):
    importer = GitHubWikiImporter()
    with ImportErrorHandler(importer, kw.get('project_name'), c.project):
        importer.import_tool(c.project, c.user, **kw)


class GitHubWikiImportForm(ToolImportForm):
    gh_project_name = fev.UnicodeString(not_empty=True)
    gh_user_name = fev.UnicodeString(not_empty=True)
    tool_option = fev.UnicodeString(if_missing=u'')


class GitHubWikiImportController(BaseController):

    def __init__(self):
        self.importer = GitHubWikiImporter()

    @property
    def target_app(self):
        return self.importer.target_app[0]

    @with_trailing_slash
    @expose('jinja:forgeimporters.github:templates/wiki/index.html')
    def index(self, **kw):
        return dict(importer=self.importer,
                    target_app=self.target_app)

    @without_trailing_slash
    @expose()
    @require_post()
    @validate(GitHubWikiImportForm(ForgeWikiApp), error_handler=index)
    def create(self, gh_project_name, gh_user_name, mount_point, mount_label, **kw):
        import_tool.post(
            project_name=gh_project_name,
            user_name=gh_user_name,
            mount_point=mount_point,
            mount_label=mount_label,
            tool_option=kw.get('tool_option'))
        flash('Wiki import has begun. Your new wiki will be available '
              'when the import is complete.')
        redirect(c.project.url() + 'admin/')


class GitHubWikiImporter(ToolImporter):
    target_app = TARGET_APPS
    controller = GitHubWikiImportController
    source = 'GitHub'
    tool_label = 'Wiki'
    tool_description = 'Import your wiki from GitHub'
    tool_option = {"import_history": "Import history"}
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
        with_history = tool_option == 'import_history'
        ThreadLocalORMSession.flush_all()
        try:
            M.session.artifact_orm_session._get().skip_mod_date = True
            with h.push_config(c, app=app):
                self.get_wiki_pages(extractor.get_page_url('wiki_url'), history=with_history)
            ThreadLocalORMSession.flush_all()
            g.post_event('project_updated')
            return app
        except Exception as e:
            h.make_app_admin_only(app)
            raise
        finally:
            M.session.artifact_orm_session._get().skip_mod_date = False

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
        for commit in reversed(list(wiki.iter_commits())):
            self.get_blobs_with_history(commit)
        rmtree(wiki_path)

    def convert_gollum_tags(self, text):
        # order is important
        text = self.convert_gollum_external_links(text)
        text = self.convert_gollum_page_links(text)
        return text

    def convert_gollum_page_links(self, text):
        _re = re.compile(r'''(?P<quote>')?            # possible tag escaping
                             (?P<tag>\[\[             # tag start
                             (?:(?P<title>[^]|]*)\|)? # optional title
                             (?P<page>[^]]+)          # page name
                             \]\])                    # tag end''', re.VERBOSE)

        def repl(match):
            page = match.group('page').replace('-', ' ').replace('/', ' ')
            title = match.groupdict().get('title')
            quote = match.groupdict().get('quote')
            if quote:
                # tag is escaped, return untouched
                return match.group('tag')
            if title:
                return u'[{}]({})'.format(title, page)
            return u'[{}]'.format(page)

        return _re.sub(repl, text)

    def convert_gollum_external_links(self, text):
        _re = re.compile(
            r'''(?P<quote>')?                     # possible tag escaping
                (?P<tag>\[\[                      # tag start
                (?:(?P<title>[^]|]*)\|)?          # optional title
                (?P<link>(?:http|https)://[^]]+)  # link
                \]\])                             # tag end''', re.VERBOSE)

        def repl(match):
            link = match.group('link')
            title = match.groupdict().get('title')
            quote = match.groupdict().get('quote')
            if quote:
                # tag is escaped, return untouched
                return match.group('tag')
            if title:
                return u'[{}]({})'.format(title, link)
            return u'<{}>'.format(link)

        return _re.sub(repl, text)
