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
from __future__ import annotations

import re

"""The application's Globals object"""

import logging
import cgi
import hashlib
import json
import datetime
from six.moves.urllib.parse import urlencode
from subprocess import Popen, PIPE
import os
import time
import traceback

import activitystream
import pkg_resources
import markdown
import pygments
import pygments.lexers
import pygments.formatters
import pygments.util
from tg import config
from tg import request
from tg import tmpl_context as c
from paste.deploy.converters import asbool, asint, aslist
from pypeline.markup import markup as pypeline_markup
from ming.odm import session, MappedClass

import ew as ew_core
import ew.jinja2_ew as ew
from ming.utils import LazyProperty
from markupsafe import Markup

import allura.tasks.event_tasks
from allura import model as M
from allura.lib.markdown_extensions import (
    ForgeExtension,
    CommitMessageExtension,
    EmojiExtension,
    UserMentionExtension
)
from allura.eventslistener import PostEvent

from allura.lib import gravatar, plugin, utils
from allura.lib import helpers as h
from allura.lib.macro import uncacheable_macros_names
from allura.lib.widgets import analytics
from allura.lib.security import Credentials
from allura.lib.solr import MockSOLR, make_solr_from_config
from allura.model.session import artifact_orm_session
import six

__all__ = ['Globals']

log = logging.getLogger(__name__)


class ForgeMarkdown(markdown.Markdown):

    def convert(self, source, render_limit=True):
        if render_limit and len(source) > asint(config.get('markdown_render_max_length', 80000)):
            # if text is too big, markdown can take a long time to process it,
            # so we return it as a plain text
            log.info('Text is too big. Skipping markdown processing')
            escaped = cgi.escape(h.really_unicode(source))
            return Markup('<pre>%s</pre>' % escaped)
        try:
            return super().convert(source)
        except Exception:
            log.info('Invalid markdown: %s  Upwards trace is %s', source,
                     ''.join(traceback.format_stack()), exc_info=True)
            escaped = h.really_unicode(source)
            escaped = cgi.escape(escaped)
            return Markup("""<p><strong>ERROR!</strong> The markdown supplied could not be parsed correctly.
            Did you forget to surround a code snippet with "~~~~"?</p><pre>%s</pre>""" % escaped)

    @LazyProperty
    def uncacheable_macro_regex(self):
        regex_names = '|'.join(uncacheable_macros_names())
        return re.compile(rf"\[\[\s*({regex_names})\b")

    def cached_convert(self, artifact: MappedClass, field_name: str) -> str:
        """
        Convert ``artifact.field_name`` markdown source to html, caching
        the result if the render time is greater than the defined threshold.

        :param artifact: often an artifact, but also can be Neighborhood, OAuthConsumerToken, etc
        """
        source_text = getattr(artifact, field_name)
        cache_field_name = field_name + '_cache'
        cache = getattr(artifact, cache_field_name, None)
        if not cache:
            log.warn(
                'Skipping Markdown caching - Missing cache field "%s" on class %s',
                field_name, artifact.__class__.__name__)
            return self.convert(source_text)

        bugfix_rev = 4  # increment this if we need all caches to invalidated (e.g. xss in markdown rendering fixed)
        md5 = None
        # If a cached version exists and it is valid, return it.
        if cache.md5 is not None:
            md5 = hashlib.md5(source_text.encode('utf-8')).hexdigest()
            if cache.md5 == md5 and getattr(cache, 'fix7528', False) == bugfix_rev:
                return Markup(cache.html)

        # Convert the markdown and time the result.
        start = time.time()
        html = self.convert(source_text, render_limit=False)
        render_time = time.time() - start

        threshold = config.get('markdown_cache_threshold')
        try:
            threshold = float(threshold) if threshold else None
        except ValueError:
            threshold = None
            log.warn('Skipping Markdown caching - The value for config param '
                     '"markdown_cache_threshold" must be a float.')

        # Check if contains macro and never cache
        if self.uncacheable_macro_regex.search(source_text):
            if render_time > float(config.get('markdown_cache_threshold.nocache', 0.5)):
                try:
                    details = artifact.index_id()
                except Exception:
                    details = str(artifact._id)
                try:
                    details += ' ' + artifact.url()
                except Exception:
                    pass
                log.info(f'Not saving markdown cache since it has a dynamic macro.  Took {render_time:.03}s on {details}')
            return html

        if threshold is not None and render_time > threshold:
            # Save the cache
            if md5 is None:
                md5 = hashlib.md5(source_text.encode('utf-8')).hexdigest()
            cache.md5, cache.html, cache.render_time = md5, html, render_time
            cache.fix7528 = bugfix_rev  # flag to indicate good caches created after [#7528] and other critical bugs were fixed.

            try:
                sess = session(artifact)
            except AttributeError:
                # this can happen if a non-artifact object is used
                log.exception('Could not get session for %s', artifact)
            else:
                with utils.skip_mod_date(artifact.__class__), \
                     utils.skip_last_updated(artifact.__class__):
                    sess.flush(artifact)
        return html


class Globals:

    """Container for objects available throughout the life of the application.

    One instance of Globals is created during application initialization and
    is available during requests via the 'app_globals' variable.

    """
    __shared_state = {}

    def __init__(self):
        self.__dict__ = self.__shared_state
        if self.__shared_state:
            return
        self.allura_templates = pkg_resources.resource_filename(
            'allura', 'templates')
        # Setup SOLR
        self.solr_server = aslist(config.get('solr.server'), ',')
        # skip empty strings in case of extra commas
        self.solr_server = [s for s in self.solr_server if s]
        self.solr_query_server = config.get('solr.query_server')
        if self.solr_server:
            self.solr = make_solr_from_config(
                self.solr_server, self.solr_query_server)
            self.solr_short_timeout = make_solr_from_config(
                self.solr_server, self.solr_query_server,
                timeout=int(config.get('solr.short_timeout', 10)))
        else:  # pragma no cover
            log.warning('Solr config not set; using in-memory MockSOLR')
            self.solr = self.solr_short_timeout = MockSOLR()

        # Load login/logout urls; only used for customized logins
        self.login_url = config.get('auth.login_url', '/auth/')
        self.logout_url = config.get('auth.logout_url', '/auth/logout')
        self.login_fragment_url = config.get(
            'auth.login_fragment_url', '/auth/login_fragment/')

        # Setup Gravatar
        self.gravatar = gravatar.url

        # Setup pygments
        self.pygments_formatter = utils.LineAnchorCodeHtmlFormatter(
            cssclass='codehilite',
            linenos='table')

        # Setup Pypeline
        self.pypeline_markup = pypeline_markup

        # Setup analytics
        accounts = config.get('ga.account', 'UA-XXXXX-X')
        accounts = accounts.split(' ')
        self.analytics = analytics.GoogleAnalytics(accounts=accounts)

        self.icons = dict(
            move=Icon('fa fa-arrows', 'Move'),
            edit=Icon('fa fa-edit', 'Edit'),
            admin=Icon('fa fa-gear', 'Admin'),
            send=Icon('fa fa-send-o', 'Send'),
            add=Icon('fa fa-plus-circle', 'Add'),
            moderate=Icon('fa fa-hand-stop-o', 'Moderate'),
            pencil=Icon('fa fa-pencil', 'Edit'),
            help=Icon('fa fa-question-circle', 'Help'),
            eye=Icon('fa fa-eye', 'View'),
            search=Icon('fa fa-search', 'Search'),
            history=Icon('fa fa-calendar', 'History'),
            feed=Icon('fa fa-rss', 'Feed'),
            mail=Icon('fa fa-envelope-o', 'Subscribe'),
            reply=Icon('fa fa-reply', 'Reply'),
            tag=Icon('fa fa-tag', 'Tag'),
            flag=Icon('fa fa-flag-o', 'Flag'),
            undelete=Icon('fa fa-undo', 'Undelete'),
            delete=Icon('fa fa-trash-o', 'Delete'),
            close=Icon('fa fa-close', 'Close'),
            table=Icon('fa fa-table', 'Table'),
            stats=Icon('fa fa-line-chart', 'Stats'),
            pin=Icon('fa fa-mail-pin', 'Pin'),
            folder=Icon('fa fa-folder', 'Folder'),
            fork=Icon('fa fa-code-fork', 'Fork'),
            merge=Icon('fa fa-code-fork upside-down', 'Merge'),
            conversation=Icon('fa fa-comments', 'Conversation'),
            group=Icon('fa fa-group', 'Group'),
            user=Icon('fa fa-user', 'User'),
            secure=Icon('fa fa-lock', 'Lock'),
            unsecure=Icon('fa fa-unlock', 'Unlock'),
            star=Icon('fa fa-star', 'Star'),
            expand=Icon('fa fa-expand', 'Maximize'),
            restore=Icon('fa fa-compress', 'Restore'),
            check=Icon('fa fa-check-circle', 'Check'),
            caution=Icon('fa fa-ban', 'Caution'),
            vote_up=Icon('fa fa-plus', 'Vote Up'),
            vote_down=Icon('fa fa-minus', 'Vote Down'),
            download=Icon('fa fa-download', 'Download'),
            revert=Icon('fa fa-history', 'Revert'),
            browse_commits=Icon('fa fa-list', 'Browse Commits'),
            file=Icon('fa fa-file-o', 'File'),
            # Permissions
            perm_read=Icon('fa fa-eye', 'Read'),
            perm_update=Icon('fa fa-rotate-left', 'Update'),
            perm_create=Icon('fa fa-flash', 'Create'),
            perm_register=Icon('fa fa-gear', 'Config'),
            perm_delete=Icon('fa fa-minus-circle', 'Remove'),
            perm_tool=Icon('fa fa-gear', 'Tool'),
            perm_admin=Icon('fa fa-gear', 'Admin'),
            perm_has_yes=Icon('fa fa-check', 'Check'),
            perm_has_no=Icon('fa fa-ban', 'No entry'),
            perm_has_inherit=Icon('fa fa-check-circle', 'Has inherit'),
        )

        # Cache some loaded entry points
        def _cache_eps(section_name, dict_cls=dict):
            d = dict_cls()
            for ep in h.iter_entry_points(section_name):
                try:
                    value = ep.load()
                except Exception:
                    log.exception('Could not load entry point [%s] %s', section_name, ep)
                else:
                    d[ep.name] = value
            return d

        class entry_point_loading_dict(dict):

            def __missing__(self, key):
                self[key] = _cache_eps(key)
                return self[key]

        self.entry_points = entry_point_loading_dict(
            tool=_cache_eps('allura', dict_cls=utils.CaseInsensitiveDict),
            auth=_cache_eps('allura.auth'),
            registration=_cache_eps('allura.project_registration'),
            theme=_cache_eps('allura.theme'),
            user_prefs=_cache_eps('allura.user_prefs'),
            spam=_cache_eps('allura.spam'),
            phone=_cache_eps('allura.phone'),
            stats=_cache_eps('allura.stats'),
            site_stats=_cache_eps('allura.site_stats'),
            admin=_cache_eps('allura.admin'),
            site_admin=_cache_eps('allura.site_admin'),
            # macro eps are used solely for ensuring that external macros are
            # imported (after load, the ep itself is not used)
            macros=_cache_eps('allura.macros'),
            webhooks=_cache_eps('allura.webhooks'),
            multifactor_totp=_cache_eps('allura.multifactor.totp'),
            multifactor_recovery_code=_cache_eps('allura.multifactor.recovery_code'),
        )

        # Set listeners to update stats
        statslisteners = []
        for name, ep in self.entry_points['stats'].items():
            statslisteners.append(ep())
        self.statsUpdater = PostEvent(statslisteners)

        self.tmpdir = os.getenv('TMPDIR', '/tmp')

    @LazyProperty
    def spam_checker(self):
        """Return a SpamFilter implementation.
        """
        from allura.lib import spam
        return spam.SpamFilter.get(config, self.entry_points['spam'])

    @LazyProperty
    def phone_service(self):
        """Return a :class:`allura.lib.phone.PhoneService` implementation"""
        from allura.lib import phone
        return phone.PhoneService.get(config, self.entry_points['phone'])

    @LazyProperty
    def director(self):
        """Return activitystream director"""
        if asbool(config.get('activitystream.recording.enabled', False)):
            return activitystream.director()
        else:
            class NullActivityStreamDirector:

                def connect(self, *a, **kw):
                    pass

                def disconnect(self, *a, **kw):
                    pass

                def is_connected(self, *a, **kw):
                    return False

                def create_activity(self, *a, **kw):
                    pass

                def create_timeline(self, *a, **kw):
                    pass

                def create_timelines(self, *a, **kw):
                    pass

                def get_timeline(self, *a, **kw):
                    return []
            return NullActivityStreamDirector()

    def post_event(self, topic, *args, **kwargs):
        if 'flush_immediately' not in kwargs:
            try:
                env = request.environ
            except AttributeError:
                script_without_ming_middleware = True
            else:
                script_without_ming_middleware = env['PATH_INFO'] == '--script--'
            if script_without_ming_middleware:
                kwargs['flush_immediately'] = True
            else:
                # within tasks and web requests, ming middleware will flush everything to mongo
                # so best to *not* flush immediately and let all db writes happen in order
                # so there's no chance of an event being created and started while the initiating code is still running
                kwargs['flush_immediately'] = False
        allura.tasks.event_tasks.event.post(topic, *args, **kwargs)

    @LazyProperty
    def theme(self):
        return plugin.ThemeProvider.get()

    @property
    def antispam(self):
        a = request.environ.get('allura.antispam')
        if a is None:
            a = request.environ['allura.antispam'] = utils.AntiSpam()
        return a

    @property
    def credentials(self):
        return Credentials.get()

    def handle_paging(self, limit, page, default=25):
        limit = self.manage_paging_preference(limit, default)
        limit = max(int(limit), 1)
        limit = min(limit, asint(config.get('limit_param_max', 500)))
        try:
            page = max(int(page), 0)
        except ValueError:
            page = 0
        start = page * int(limit)
        return (limit, page, start)

    def manage_paging_preference(self, limit, default=25):
        if not limit:
            if c.user in (None, M.User.anonymous()):
                limit = default
            else:
                limit = c.user.get_pref('results_per_page') or default
        try:
            limit = int(limit)
        except ValueError:
            limit = default
        return limit

    def document_class(self, neighborhood):
        classes = ''
        if neighborhood:
            classes += ' neighborhood-%s' % neighborhood.name
        if not neighborhood and c.project:
            classes += ' neighborhood-%s' % c.project.neighborhood.name
        if c.project:
            classes += ' project-%s' % c.project.shortname
        if c.app:
            classes += ' mountpoint-%s' % c.app.config.options.mount_point
        return classes

    def highlight(self, text, lexer=None, filename=None):
        if not text:
            if lexer == 'diff':
                return Markup('<em>File contents unchanged</em>')
            return Markup('<em>Empty file</em>')
        # Don't use line numbers for diff highlight's, as per [#1484]
        if lexer == 'diff':
            formatter = pygments.formatters.HtmlFormatter(cssclass='codehilite', linenos=False)
        else:
            formatter = self.pygments_formatter
        text = h.really_unicode(text)
        if lexer is None:
            if len(text) < asint(config.get('scm.view.max_syntax_highlight_bytes', 500000)):
                try:
                    lexer = pygments.lexers.get_lexer_for_filename(filename, encoding='chardet')
                except pygments.util.ClassNotFound:
                    pass
        else:
            lexer = pygments.lexers.get_lexer_by_name(lexer, encoding='chardet')

        if lexer is None or len(text) >= asint(config.get('scm.view.max_syntax_highlight_bytes', 500000)):
            # no highlighting, but we should escape, encode, and wrap it in
            # a <pre>
            text = cgi.escape(text)
            return Markup('<pre>' + text + '</pre>')
        else:
            return Markup(pygments.highlight(text, lexer, formatter))

    def forge_markdown(self, **kwargs):
        '''return a markdown.Markdown object on which you can call convert'''
        return ForgeMarkdown(
            extensions=['markdown.extensions.fenced_code', 'markdown.extensions.codehilite',
                        'markdown.extensions.abbr', 'markdown.extensions.def_list', 'markdown.extensions.footnotes',
                        'markdown.extensions.md_in_html',
                        ForgeExtension(**kwargs), EmojiExtension(), UserMentionExtension(),
                        'markdown.extensions.tables', 'markdown.extensions.toc', 'markdown.extensions.nl2br',
                        'markdown_checklist.extension'],
            output_format='html')

    @property
    def markdown(self):
        return self.forge_markdown()

    @property
    def markdown_wiki(self):
        if c.project and c.project.is_nbhd_project:
            return self.forge_markdown(wiki=True, macro_context='neighborhood-wiki')
        elif c.project and c.project.is_user_project:
            return self.forge_markdown(wiki=True, macro_context='userproject-wiki')
        else:
            return self.forge_markdown(wiki=True)

    @property
    def markdown_commit(self):
        """Return a Markdown parser configured for rendering commit messages.

        """
        app = getattr(c, 'app', None)
        return ForgeMarkdown(extensions=[CommitMessageExtension(app), EmojiExtension(), 'markdown.extensions.nl2br'],
                             output_format='html')

    @property
    def production_mode(self):
        return asbool(config.get('debug')) is False

    @LazyProperty
    def user_message_time_interval(self):
        """The rolling window of time (in seconds) during which no more than
        :meth:`user_message_max_messages` may be sent by any one user.

        """
        return int(config.get('user_message.time_interval', 3600))

    @LazyProperty
    def user_message_max_messages(self):
        """The number of user messages that can be sent within
        meth:`user_message_time_interval` before rate-limiting is enforced.

        """
        return int(config.get('user_message.max_messages', 20))

    @LazyProperty
    def server_name(self):
        p1 = Popen(['hostname', '-s'], stdout=PIPE)
        server_name = p1.communicate()[0].strip()
        p1.wait()
        return six.ensure_text(server_name)

    @property
    def tool_icon_css(self):
        """Return a (css, md5) tuple, where ``css`` is a string of CSS
        containing class names and icon urls for every installed tool, and
        ``md5`` is the md5 hexdigest of ``css``.

        """
        css = ''
        for tool_name in self.entry_points['tool']:
            for size in (24, 32, 48):
                url = self.theme.app_icon_url(tool_name.lower(), size)
                css += '.ui-icon-tool-%s-%i {background: url(%s) no-repeat;}\n' % (
                    tool_name, size, url)
        return css, hashlib.md5(css.encode('utf-8')).hexdigest()

    @property
    def resource_manager(self):
        return ew_core.widget_context.resource_manager

    def register_css(self, href, **kw):
        self.resource_manager.register(ew.CSSLink(href, **kw))

    def register_js(self, href, **kw):
        self.resource_manager.register(ew.JSLink(href, **kw))

    def register_forge_css(self, href, **kw):
        self.resource_manager.register(ew.CSSLink('allura/' + href, **kw))

    def register_forge_js(self, href, **kw):
        self.resource_manager.register(ew.JSLink('allura/' + href, **kw))

    def register_app_css(self, href, **kw):
        app = kw.pop('app', c.app)
        self.resource_manager.register(
            ew.CSSLink(f'tool/{app.config.tool_name.lower()}/{href}', **kw))

    def register_app_js(self, href, **kw):
        app = kw.pop('app', c.app)
        self.resource_manager.register(
            ew.JSLink(f'tool/{app.config.tool_name.lower()}/{href}', **kw))

    def register_theme_css(self, href, **kw):
        self.resource_manager.register(ew.CSSLink(self.theme_href(href), **kw))

    def register_theme_js(self, href, **kw):
        self.resource_manager.register(ew.JSLink(self.theme_href(href), **kw))

    def register_js_snippet(self, text, **kw):
        self.resource_manager.register(ew.JSScript(text, **kw))

    def theme_href(self, href):
        return self.theme.href(href)

    def forge_static(self, resource):
        base = config['static.url_base']
        if base.startswith(':'):
            base = request.scheme + base
        return base + resource

    @property
    def user_profile_urls_with_profile_path(self):
        return asbool(config['user_profile_url_with_profile_path'])

    def user_profile_disabled_tools(self):
        return aslist(config.get('user_prefs.disabled_tools',''), sep=',')

    def app_static(self, resource, app=None):
        base = config['static.url_base']
        app = app or c.app
        if base.startswith(':'):
            base = request.scheme + base
        return (base + app.config.tool_name.lower() + '/' + resource)

    def set_project(self, pid_or_project):
        'h.set_context() is preferred over this method'
        if isinstance(pid_or_project, M.Project):
            c.project = pid_or_project
        elif isinstance(pid_or_project, str):
            raise TypeError('need a Project instance, got %r' % pid_or_project)
        elif pid_or_project is None:
            c.project = None
        else:
            c.project = None
            log.error('Trying g.set_project(%r)', pid_or_project)

    def set_app(self, name):
        'h.set_context() is preferred over this method'
        c.app = c.project.app_instance(name)

    def year(self):
        return datetime.datetime.utcnow().year

    @LazyProperty
    def noreply(self):
        return str(config.get('noreply', 'noreply@%s' % config['domain']))

    @property
    def build_key(self):
        return config.get('build_key', '')

    @LazyProperty
    def global_nav(self):
        if not config.get('global_nav', False):
            return []

        return json.loads(config.get('global_nav'))

    @LazyProperty
    def nav_logo(self):
        logo = dict(
            redirect_link=config.get('logo.link', False),
            image_path=config.get('logo.path', False),
            image_width=config.get('logo.width', False),
            image_height=config.get('logo.height', False)
        )
        if not logo['redirect_link']:
            logo['redirect_link'] = '/'

        if not logo['image_path']:
            log.warning('Image path not set for nav_logo')
            return False

        allura_path = os.path.dirname(os.path.dirname(__file__))
        image_full_path = '{}/public/nf/images/{}'.format(
            allura_path, logo['image_path'])

        if not os.path.isfile(image_full_path):
            log.warning('Could not find logo at: %s' % image_full_path)
            return False

        path = 'images/%s' % logo['image_path']
        return {
            "image_path": self.forge_static(path),
            "redirect_link": logo['redirect_link'],
            "image_width": logo['image_width'],
            "image_height": logo['image_height']
        }

    @property
    def commit_statuses_enabled(self):
        return asbool(config['scm.commit_statuses'])

class Icon:

    def __init__(self, css, title=None):
        self.css = css
        self.title = title or ''

    def render(self, show_title=False, extra_css=None, closing_tag=True, tag='a', **kw):
        title = kw.get('title') or self.title
        attrs = {
            'title': title,
            'class': ' '.join(['icon', extra_css or '']).strip(),
        }
        if tag == 'a':
            attrs['href'] = '#'
        attrs.update(kw)
        attrs = ew._Jinja2Widget().j2_attrs(attrs)
        visible_title = ''
        if show_title:
            visible_title = f'&nbsp;{Markup.escape(title)}'
        closing_tag = f'</{tag}>' if closing_tag else ''
        icon = f'<{tag} {attrs}><i class="{self.css}"></i>{visible_title}{closing_tag}'
        return Markup(icon)
