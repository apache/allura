# -*- coding: utf-8 -*-

"""The application's Globals object"""

__all__ = ['Globals']
import logging
import socket
import cgi
import json
import shlex
import datetime
from urllib import urlencode
from ConfigParser import RawConfigParser
from collections import defaultdict

import pkg_resources

import pysolr
import markdown
import pygments
import pygments.lexers
import pygments.formatters
import pygments.util
import webob.exc
from tg import config, session
from tg import c, request
from paste.deploy.converters import asbool, asint
from pypeline.markup import markup as pypeline_markup

import ew as ew_core
import ew.jinja2_ew as ew

import allura.tasks.event_tasks
from allura import model as M
from allura.lib.markdown_extensions import ForgeExtension

from allura.lib import gravatar, plugin, utils
from allura.lib import helpers as h
from allura.lib.widgets import analytics
from allura.lib.security import Credentials
from allura.lib.async import Connection, MockAMQ

log = logging.getLogger(__name__)

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
            self.solr = MockSOLR()
        elif self.solr_server:
            self.solr =  pysolr.Solr(self.solr_server)
        else: # pragma no cover
            self.solr = None
        self.use_queue = asbool(config.get('use_queue', False))

        # Load login/logout urls; only used for SFX logins
        self.login_url = config.get('auth.login_url', '/auth/')
        self.logout_url = config.get('auth.logout_url', '/auth/logout')

        # Setup RabbitMQ
        if asbool(config.get('amqp.enabled', 'true')):
            if asbool(config.get('amqp.mock')):
                self.amq_conn = self.mock_amq = MockAMQ(self)
            else:
                self.amq_conn = Connection(
                    hostname=config.get('amqp.hostname', 'localhost'),
                    port=asint(config.get('amqp.port', 5672)),
                    userid=config.get('amqp.userid', 'testuser'),
                    password=config.get('amqp.password', 'testpw'),
                    vhost=config.get('amqp.vhost', 'testvhost'))
        else:
            self.amq_conn = None

        # Setup Gravatar
        self.gravatar = gravatar.url

        self.oid_store = M.OpenIdStore()

        # Setup pygments
        self.pygments_formatter = pygments.formatters.HtmlFormatter(
            cssclass='codehilite',
            linenos='inline')

        # Setup Pypeline
        self.pypeline_markup = pypeline_markup

        # Setup analytics
        self.analytics = analytics.GoogleAnalytics(account=config.get('ga.account', 'UA-32013-57'))

        # Setup theme
        self.theme = plugin.ThemeProvider.get()

        self.icons = dict(
            admin = Icon('x', 'ico-admin'),
            pencil = Icon('p', 'ico-pencil'),
            help = Icon('h', 'ico-help'),
            search = Icon('s', 'ico-search'),
            history = Icon('N', 'ico-history'),
            feed = Icon('f', 'ico-feed'),
            mail = Icon('M', 'ico-mail'),
            reply = Icon('w', 'ico-reply'),
            tag = Icon('z', 'ico-tag'),
            flag = Icon('^', 'ico-flag'),
            undelete = Icon('+', 'ico-undelete'),
            delete = Icon('#', 'ico-delete'),
            close = Icon('D', 'ico-close'),
            table = Icon('n', 'ico-table'),
            stats = Icon('Y', 'ico-stats'),
            pin = Icon('@', 'ico-pin'),
            folder = Icon('o', 'ico-folder'),
            fork = Icon('R', 'ico-fork'),
            merge = Icon('J', 'ico-merge'),
            plus = Icon('+', 'ico-plus'),
            conversation = Icon('q', 'ico-conversation'),
            group = Icon('g', 'ico-group'),
            user = Icon('U', 'ico-user'),
            # Permissions
            perm_read = Icon('E', 'ico-focus'),
            perm_update = Icon('0', 'ico-sync'),
            perm_create = Icon('e', 'ico-config'),
            perm_register = Icon('e', 'ico-config'),
            perm_delete = Icon('-', 'ico-minuscirc'),
            perm_tool = Icon('x', 'ico-config'),
            perm_admin = Icon('(', 'ico-lock'),
        )

    def post_event(self, topic, *args, **kwargs):
        allura.tasks.event_tasks.event.post(topic, *args, **kwargs)

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
        if limit:
            if c.user in (None, M.User.anonymous()):
                session['results_per_page'] = int(limit)
            else:
                c.user.set_pref('results_per_page', int(limit))
        else:
            if c.user in (None, M.User.anonymous()):
                limit = 'results_per_page' in session and session['results_per_page'] or default
            else:
                limit = c.user.get_pref('results_per_page') or default
        page = max(int(page), 0)
        start = page * int(limit)
        return (limit, page, start)

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
        return markdown.Markdown(
                extensions=['codehilite', ForgeExtension(**kwargs), 'tables'],
                output_format='html4')

    @property
    def markdown(self):
        return self.forge_markdown()

    @property
    def markdown_wiki(self):
        return self.forge_markdown(wiki=True)

    @property
    def production_mode(self):
        return asbool(config.get('debug')) == False

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
            ew.CSSLink('tool/%s/%s' % (app.config.tool_name, href), **kw))

    def register_app_js(self, href, **kw):
        app = kw.pop('app', c.app)
        self.resource_manager.register(
            ew.JSLink('tool/%s/%s' % (app.config.tool_name, href), **kw))

    def register_js_snippet(self, text, **kw):
        self.resource_manager.register(
            ew.JSScript(text, **kw))

    def oid_session(self):
        if 'openid_info' in session:
            return session['openid_info']
        else:
            session['openid_info'] = result = {}
            return result

    def forge_static(self, resource):
        base = config['static.url_base']
        if base.startswith(':'):
            base = request.scheme + base
        return base + resource

    def theme_static(self, resource):
        if isinstance(resource,tuple):
            theme_name = resource[1]
            resource = resource[0]
        else:
            theme_name = config.get('theme', 'allura')
        base = config['static.url_base']
        if base.startswith(':'):
            base = request.scheme + base
        return base + theme_name + '/' + resource

    def app_static(self, resource, app=None):
        base = config['static.url_base']
        app = app or c.app
        if base.startswith(':'):
            base = request.scheme + base
        return (base + app.config.tool_name + '/' + resource)

    def set_project(self, pid):
        c.project = M.Project.query.get(shortname=pid, deleted=False)

    def set_app(self, name):
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

class MockSOLR(object):

    class MockHits(list):
        @property
        def hits(self):
            return len(self)

        @property
        def docs(self):
            return self

    def __init__(self):
        self.db = {}

    def add(self, objects):
        for o in objects:
            o['text'] = ''.join(o['text'])
            self.db[o['id']] = o

    def commit(self):
        pass

    def search(self, q, fq=None, **kw):
        if isinstance(q, unicode):
            q = q.encode('latin-1')
        # Parse query
        preds = []
        q_parts = shlex.split(q)
        if fq: q_parts += fq
        for part in q_parts:
            if part == '&&':
                continue
            if ':' in part:
                field, value = part.split(':', 1)
                preds.append((field, value))
            else:
                preds.append(('text', part))
        result = self.MockHits()
        for obj in self.db.values():
            for field, value in preds:
                neg = False
                if field[0] == '!':
                    neg = True
                    field = field[1:]
                if field == 'text' or field.endswith('_t'):
                    if (value not in str(obj.get(field, ''))) ^ neg:
                        break
                else:
                    if (value != str(obj.get(field, ''))) ^ neg:
                        break
            else:
                result.append(obj)
        return result

    def delete(self, *args, **kwargs):
        if kwargs.get('q', None) == '*:*':
            self.db = {}
        elif kwargs.get('id', None):
            del self.db[kwargs['id']]
        elif kwargs.get('q', None):
            for doc in self.search(kwargs['q']):
                self.delete(id=doc['id'])

class Icon(object):
    def __init__(self, char, css):
        self.char = char
        self.css = css

def connect_amqp(config):
    return
