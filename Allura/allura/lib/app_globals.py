# -*- coding: utf-8 -*-

"""The application's Globals object"""

__all__ = ['Globals']
import logging
import cgi
import json
import datetime
from urllib import urlencode
from subprocess import Popen, PIPE

import activitystream
import pkg_resources
import markdown
import pygments
import pygments.lexers
import pygments.formatters
import pygments.util
from tg import config, session
from pylons import request
from pylons import tmpl_context as c
from paste.deploy.converters import asbool, asint
from pypeline.markup import markup as pypeline_markup

import ew as ew_core
import ew.jinja2_ew as ew
from ming.utils import LazyProperty

import allura.tasks.event_tasks
from allura import model as M
from allura.lib.markdown_extensions import ForgeExtension

from allura.lib import gravatar, plugin, utils
from allura.lib import helpers as h
from allura.lib.widgets import analytics
from allura.lib.security import Credentials
from allura.lib.async import Connection, MockAMQ
from allura.lib.solr import Solr, MockSOLR
from allura.lib.zarkov_helpers import ZarkovClient, zmq

log = logging.getLogger(__name__)


class ForgeMarkdown(markdown.Markdown):
    def convert(self, source):
        try:
            return markdown.Markdown.convert(self, source)
        except Exception:
            log.info('Invalid markdown: %s', source, exc_info=True)
            escaped = h.really_unicode(source)
            escaped = cgi.escape(escaped)
            return h.html.literal(u"""<p><strong>ERROR!</strong> The markdown supplied could not be parsed correctly.
            Did you forget to surround a code snippet with "~~~~"?</p><pre>%s</pre>""" % escaped)


class Globals(object):
    """Container for objects available throughout the life of the application.

    One instance of Globals is created during application initialization and
    is available during requests via the 'app_globals' variable.

    """
    __shared_state = {}

    def __init__(self):
        self.__dict__ = self.__shared_state
        if self.__shared_state: return
        self.allura_templates = pkg_resources.resource_filename('allura', 'templates')

        # Setup SOLR
        self.solr_server = config.get('solr.server')
        if asbool(config.get('solr.mock')):
            self.solr = self.solr_short_timeout = MockSOLR()
        elif self.solr_server:
            self.solr = Solr(self.solr_server, commit=asbool(config.get('solr.commit', True)),
                    commitWithin=config.get('solr.commitWithin'), timeout=int(config.get('solr.long_timeout', 60)))
            self.solr_short_timeout = Solr(self.solr_server, commit=asbool(config.get('solr.commit', True)),
                    commitWithin=config.get('solr.commitWithin'), timeout=int(config.get('solr.short_timeout', 10)))
        else: # pragma no cover
            self.solr = None
            self.solr_short_timeout = None
        self.use_queue = asbool(config.get('use_queue', False))

        # Load login/logout urls; only used for SFX logins
        self.login_url = config.get('auth.login_url', '/auth/')
        self.logout_url = config.get('auth.logout_url', '/auth/logout')

        # Setup Gravatar
        self.gravatar = gravatar.url

        self.oid_store = M.OpenIdStore()

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
            admin=Icon('x', 'ico-admin'),
            pencil=Icon('p', 'ico-pencil'),
            help=Icon('h', 'ico-help'),
            search=Icon('s', 'ico-search'),
            history=Icon('N', 'ico-history'),
            feed=Icon('f', 'ico-feed'),
            mail=Icon('M', 'ico-mail'),
            reply=Icon('w', 'ico-reply'),
            tag=Icon('z', 'ico-tag'),
            flag=Icon('^', 'ico-flag'),
            undelete=Icon('+', 'ico-undelete'),
            delete=Icon('#', 'ico-delete'),
            close=Icon('D', 'ico-close'),
            table=Icon('n', 'ico-table'),
            stats=Icon('Y', 'ico-stats'),
            pin=Icon('@', 'ico-pin'),
            folder=Icon('o', 'ico-folder'),
            fork=Icon('R', 'ico-fork'),
            merge=Icon('J', 'ico-merge'),
            plus=Icon('+', 'ico-plus'),
            conversation=Icon('q', 'ico-conversation'),
            group=Icon('g', 'ico-group'),
            user=Icon('U', 'ico-user'),
            secure=Icon('(', 'ico-lock'),
            unsecure=Icon(')', 'ico-unlock'),
            star=Icon('S', 'ico-star'),
            watch=Icon('E', 'ico-watch'),
            # Permissions
            perm_read=Icon('E', 'ico-focus'),
            perm_update=Icon('0', 'ico-sync'),
            perm_create=Icon('e', 'ico-config'),
            perm_register=Icon('e', 'ico-config'),
            perm_delete=Icon('-', 'ico-minuscirc'),
            perm_tool=Icon('x', 'ico-config'),
            perm_admin=Icon('(', 'ico-lock'),
            perm_has_yes=Icon('3', 'ico-check'),
            perm_has_no=Icon('d', 'ico-noentry'),
            perm_has_inherit=Icon('2', 'ico-checkcircle'),
        )

        # Cache some loaded entry points
        def _cache_eps(section_name, dict_cls=dict):
            d = dict_cls()
            for ep in pkg_resources.iter_entry_points(section_name):
                value = ep.load()
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
            )

        # Zarkov logger
        self._zarkov = None

        self.show_userstats = False
        # Set listeners to update stats
        self.statslisteners = []
        for ep in pkg_resources.iter_entry_points("allura.stats"):
            if ep.name.lower() == 'userstats':
                self.show_userstats = config.get(
                    'user.stats.enable','false')=='true'
                if self.show_userstats:
                    self.statslisteners.append(ep.load()().listener)
            else:
                self.statslisteners.append(ep.load()().listener)


    @LazyProperty
    def spam_checker(self):
        """Return a SpamFilter implementation.
        """
        from allura.lib import spam
        return spam.SpamFilter.get(config, self.entry_points['spam'])

    @LazyProperty
    def director(self):
        """Return activitystream director"""
        if asbool(config.get('activitystream.recording.enabled', False)):
            return activitystream.director()
        else:
            class NullActivityStreamDirector(object):
                def connect(self, *a, **kw):
                    pass
                def disconnect(self, *a, **kw):
                    pass
                def is_connected(self, *a, **kw):
                    return False
                def create_activity(self, *a, **kw):
                    pass
                def get_timeline(self, *a, **kw):
                    return []
            return NullActivityStreamDirector()

    @LazyProperty
    def amq_conn(self):
        if asbool(config.get('amqp.enabled', 'true')):
            if asbool(config.get('amqp.mock')):
                return MockAMQ(self)
            else:
                return Connection(
                    hostname=config.get('amqp.hostname', 'localhost'),
                    port=asint(config.get('amqp.port', 5672)),
                    userid=config.get('amqp.userid', 'testuser'),
                    password=config.get('amqp.password', 'testpw'),
                    vhost=config.get('amqp.vhost', 'testvhost'))
        else:
            return None

    def post_event(self, topic, *args, **kwargs):
        allura.tasks.event_tasks.event.post(topic, *args, **kwargs)

    def zarkov_event(
        self, event_type,
        user=None, neighborhood=None, project=None, app=None,
        extra=None):
        context = dict(
            user=None,
            neighborhood=None, project=None, tool=None,
            mount_point=None,
            is_project_member=False)

        if not zmq:
            return

        user = user or getattr(c, 'user', None)
        project = project or getattr(c, 'project', None)
        app = app or getattr(c, 'app', None)
        if user: context['user'] = user.username
        if project:
            context.update(
                project=project.shortname,
                neighborhood=project.neighborhood.url_prefix.strip('/'))
            if user:
                cred = Credentials.get()
                if cred is not None:
                    for pr in cred.user_roles(user._id, project._id).reaching_roles:
                        if pr.get('name') and pr.get('name')[0] != '*':
                            context['is_project_member'] = True
        if app:
            context.update(
                tool=app.config.tool_name,
                mount_point=app.config.options.mount_point)

        try:
            if self._zarkov is None:
                self._zarkov = ZarkovClient(
                    config.get('zarkov.host', 'tcp://127.0.0.1:6543'))
            self._zarkov.event(event_type, context, extra)
        except Exception, ex:
            self._zarkov = None
            log.error('Error sending zarkov event(%r): %r', ex, dict(
                    type=event_type, context=context, extra=extra))

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

    def handle_paging(self, limit, page, default=50):
        limit = self.manage_paging_preference(limit, default)
        page = max(int(page), 0)
        start = page * int(limit)
        return (limit, page, start)

    def manage_paging_preference(self, limit, default=50):
        if limit:
            if c.user in (None, M.User.anonymous()):
                session['results_per_page'] = int(limit)
                session.save()
            else:
                c.user.set_pref('results_per_page', int(limit))
        else:
            if c.user in (None, M.User.anonymous()):
                limit = 'results_per_page' in session and session['results_per_page'] or default
            else:
                limit = c.user.get_pref('results_per_page') or default
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
            return h.html.literal('<em>Empty file</em>')
        # Don't use line numbers for diff highlight's, as per [#1484]
        if lexer == 'diff':
            formatter = pygments.formatters.HtmlFormatter(cssclass='codehilite', linenos=False)
        else:
            formatter = self.pygments_formatter
        if lexer is None:
            try:
                lexer = pygments.lexers.get_lexer_for_filename(filename, encoding='chardet')
            except pygments.util.ClassNotFound:
                # no highlighting, but we should escape, encode, and wrap it in a <pre>
                text = h.really_unicode(text)
                text = cgi.escape(text)
                return h.html.literal(u'<pre>' + text + u'</pre>')
        else:
            lexer = pygments.lexers.get_lexer_by_name(lexer, encoding='chardet')
        return h.html.literal(pygments.highlight(text, lexer, formatter))

    def forge_markdown(self, **kwargs):
        '''return a markdown.Markdown object on which you can call convert'''
        return ForgeMarkdown(
                extensions=['codehilite', ForgeExtension(**kwargs), 'tables', 'toc', 'nl2br'], # 'fenced_code'
                output_format='html4')

    @property
    def markdown(self):
        return self.forge_markdown()

    @property
    def markdown_wiki(self):
        if c.project.is_nbhd_project:
            return self.forge_markdown(wiki=True, macro_context='neighborhood-wiki')
        elif c.project.is_user_project:
            return self.forge_markdown(wiki=True, macro_context='userproject-wiki')
        else:
            return self.forge_markdown(wiki=True)

    @property
    def production_mode(self):
        return asbool(config.get('debug')) == False

    @LazyProperty
    def server_name(self):
        p1 = Popen(['hostname', '-s'], stdout=PIPE)
        server_name = p1.communicate()[0].strip()
        p1.wait()
        return server_name

    @property
    def resource_manager(self):
        return ew_core.widget_context.resource_manager

    def register_forge_css(self, href, **kw):
        self.resource_manager.register(ew.CSSLink('allura/' + href, **kw))

    def register_forge_js(self, href, **kw):
        self.resource_manager.register(ew.JSLink('allura/' + href, **kw))

    def register_app_css(self, href, **kw):
        app = kw.pop('app', c.app)
        self.resource_manager.register(
            ew.CSSLink('tool/%s/%s' % (app.config.tool_name.lower(), href), **kw))

    def register_app_js(self, href, **kw):
        app = kw.pop('app', c.app)
        self.resource_manager.register(
            ew.JSLink('tool/%s/%s' % (app.config.tool_name.lower(), href), **kw))

    def register_theme_css(self, href, **kw):
        self.resource_manager.register(ew.CSSLink(self.theme_href(href), **kw))

    def register_theme_js(self, href, **kw):
        self.resource_manager.register(ew.JSLink(self.theme_href(href), **kw))

    def register_js_snippet(self, text, **kw):
        self.resource_manager.register(ew.JSScript(text, **kw))

    def theme_href(self, href):
        theme_name = config.get('theme', 'allura')
        return self.resource_manager.absurl(
            'theme/%s/%s' % (theme_name, href))

    def oid_session(self):
        if 'openid_info' in session:
            return session['openid_info']
        else:
            session['openid_info'] = result = {}
            session.save()
            return result

    def forge_static(self, resource):
        base = config['static.url_base']
        if base.startswith(':'):
            base = request.scheme + base
        return base + resource

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
        elif isinstance(pid_or_project, basestring):
            raise TypeError('need a Project instance, got %r' % pid_or_project)
        elif pid_or_project is None:
            c.project = None
        else:
            c.project = None
            log.error('Trying g.set_project(%r)', pid_or_project)

    def set_app(self, name):
        'h.set_context() is preferred over this method'
        c.app = c.project.app_instance(name)

    def url(self, base, **kw):
        params = urlencode(kw)
        if params:
            return '%s://%s%s?%s' % (request.scheme, request.host, base, params)
        else:
            return '%s://%s%s' % (request.scheme, request.host, base)

    def postload_contents(self):
        text = '''
'''
        return json.dumps(dict(text=text))

    def year(self):
        return datetime.datetime.utcnow().year

class Icon(object):
    def __init__(self, char, css):
        self.char = char
        self.css = css

def connect_amqp(config):
    return
