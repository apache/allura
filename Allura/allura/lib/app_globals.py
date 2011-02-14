# -*- coding: utf-8 -*-

"""The application's Globals object"""

__all__ = ['Globals']
import logging
import socket
import re
import cgi
import json
import shlex
import datetime
from urllib import urlencode
from ConfigParser import RawConfigParser
from collections import defaultdict

import pkg_resources

import mock
import pysolr
import oembed
import markdown
from pypeline.markup import markup as pypeline_markup
import pygments
import pygments.lexers
import pygments.formatters
import pygments.util
from tg import config, session
from pylons import c, request
from carrot.connection import BrokerConnection
from carrot.messaging import Publisher
from bson import ObjectId
from paste.deploy.converters import asint, asbool

import ew as ew_core
import ew.jinja2_ew as ew

from allura import model as M
from allura.lib.markdown_extensions import ForgeExtension

from allura.lib import gravatar, plugin
from allura.lib import helpers as h
from allura.lib.widgets import analytics
from allura.lib.security import Credentials

log = logging.getLogger(__name__)

class Globals(object):
    """Container for objects available throughout the life of the application.

    One instance of Globals is created during application initialization and
    is available during requests via the 'app_globals' variable.

    """

    def __init__(self):
        """Do nothing, by default."""
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
        if asbool(config.get('amqp.mock')):
            self.mock_amq = MockAMQ()
            self._publish = self.mock_amq.publish

        # Setup OEmbed
        cp = RawConfigParser()
        cp.read(config['oembed.config'])
        self.oembed_consumer = consumer = oembed.OEmbedConsumer()
        for endpoint in cp.sections():
            values = [ v for k,v in cp.items(endpoint) ]
            consumer.addEndpoint(oembed.OEmbedEndpoint(endpoint, values))

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
            perm_delete = Icon('-', 'ico-minuscirc'),
            perm_tool = Icon('x', 'ico-config'),
            perm_security = Icon('(', 'ico-lock'),
        )

    @property
    def credentials(self):
        return Credentials.get()

    def handle_paging(self, limit, page, default=50):
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
        if lexer is None:
            try:
                lexer = pygments.lexers.get_lexer_for_filename(filename, encoding='chardet')
            except pygments.util.ClassNotFound:
                # no highlighting, but we should escape, encode, and wrap it in a <pre>
                text = h.really_unicode(text)
                text = cgi.escape(text)
                return u'<pre>' + text + u'</pre>'
        else:
            lexer = pygments.lexers.get_lexer_by_name(lexer, encoding='chardet')
        return h.html.literal(pygments.highlight(text, lexer, self.pygments_formatter))

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

    @property
    def publisher(self):
        from .custom_middleware import environ
        if 'allura.carrot.publisher' not in environ:
            environ['allura.carrot.publisher'] = dict(
                audit=Publisher(connection=self.conn, exchange='audit', auto_declare=False),
                react=Publisher(connection=self.conn, exchange='react', auto_declare=False))
        return environ['allura.carrot.publisher']

    @property
    def conn(self):
        if asbool(config.get('amqp.mock')):
            return self.mock_amq
        from .custom_middleware import environ
        if 'allura.carrot.connection' not in environ:
            environ['allura.carrot.connection'] = BrokerConnection(
                hostname=config.get('amqp.hostname', 'localhost'),
                port=asint(config.get('amqp.port', 5672)),
                userid=config.get('amqp.userid', 'testuser'),
                password=config.get('amqp.password', 'testpw'),
                virtual_host=config.get('amqp.vhost', 'testvhost'))
        return environ['allura.carrot.connection']

    def amqp_reconnect(self):
        from .custom_middleware import environ
        try:
            self.conn.close()
        except:
            log.exception('Error closing amqp connection')
        del environ['allura.carrot.connection']
        self.conn

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

    def publish(self, xn, key, message=None, **kw):
        project = getattr(c, 'project', None)
        app = getattr(c, 'app', None)
        user = getattr(c, 'user', None)
        if message is None: message = {}
        if project:
            message.setdefault('project_id', project._id)
        if app:
            message.setdefault('mount_point', app.config.options.mount_point)
        if user:
            if user._id is None:
                message.setdefault('user_id',  None)
            else:
                message.setdefault('user_id',  user._id)
        # Make message safe for serialization
        if kw.get('serializer', 'json') in ('json', 'yaml'):
            for k, v in message.items():
                if isinstance(v, ObjectId):
                    message[k] = str(v)
        if getattr(c, 'queued_messages', None) is not None:
            c.queued_messages.append(dict(
                    xn=xn,
                    message=message,
                    routing_key=key,
                    **kw))
        else:
            self._publish(xn, message, routing_key=key, **kw)

    def _publish(self, xn, message, routing_key, **kw):
        try:
            self.publisher[xn].send(message, routing_key=routing_key, **kw)
        except socket.error: # pragma no cover
            return
            log.exception('''Failure publishing message:
xn         : %r
routing_key: %r
data       : %r
''', xn, routing_key, message)

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

    def __init__(self):
        self.db = {}

    def add(self, objects):
        for o in objects:
            o['text'] = ''.join(o['text'])
            self.db[o['id']] = o

    def search(self, q, fq=None, **kw):
        # Parse query
        preds = []
        q_parts = shlex.split(q)
        if fq: q_parts += fq
        for part in q_parts:
            if ':' in part:
                field, value = part.split(':', 1)
                preds.append((field, value))
            else:
                preds.append(('text', part))
        result = self.MockHits()
        for obj in self.db.values():
            for field, value in preds:
                if field == 'text' or field.endswith('_t'):
                    if value not in str(obj.get(field, '')):
                        break
                else:
                    if value != str(obj.get(field, '')):
                        break
            else:
                result.append(obj)
        return result

    def delete(self, *args, **kwargs):
        pass

class MockAMQ(object):

    def __init__(self):
        self.exchanges = defaultdict(list)
        self.queue_bindings = defaultdict(list)

    def clear(self):
        for k in self.exchanges.keys():
            self.exchanges[k][:] = []

    def create_backend(self):
        return mock.Mock()

    def publish(self, xn, message, routing_key, **kw):
        self.exchanges[xn].append(
            dict(routing_key=routing_key, message=message, kw=kw))

    def pop(self, xn):
        return self.exchanges[xn].pop(0)

    def setup_handlers(self):
        from allura.command.reactor import tool_consumers, ReactorCommand
        from allura.command import base
        self.queue_bindings = defaultdict(list)
        base.log = logging.getLogger('allura.command')
        base.M = M
        self.tools = []
        for ep in pkg_resources.iter_entry_points('allura'):
            try:
                self.tools.append((ep.name, ep.load()))
            except ImportError:
                log.warning('Canot load entry point %s', ep)
        self.reactor = ReactorCommand('reactor_setup')
        self.reactor.parse_args([])
        for name, tool in self.tools:
            for method, xn, qn, keys in tool_consumers(name, tool):
                for k in keys:
                    self.queue_bindings[xn].append(
                        dict(key=k, tool_name=name, method=method))
            # self.setup_tool(name, tool)

    def handle(self, xn):
        msg = self.pop(xn)
        for handler in self.queue_bindings[xn]:
            if self._route_matches(handler['key'], msg['routing_key']):
                self._route(xn, msg, handler['tool_name'], handler['method'])

    def handle_all(self):
        for xn, messages in self.exchanges.items():
            while messages:
                self.handle(xn)

    def _route(self, xn, msg, tool_name, method):
        import mock
        if xn == 'audit':
            callback = self.reactor.route_audit(tool_name, method)
        else:
            callback = self.reactor.route_react(tool_name, method)
        data = msg['message']
        message = mock.Mock()
        message.delivery_info = dict(
            routing_key=msg['routing_key'])
        message.ack = lambda:None
        return callback(data, message)

    def _route_matches(self, pattern, key):
        re_pattern = (pattern
                      .replace('.', r'\.')
                      .replace('*', r'(?:\w+)')
                      .replace('#', r'(?:\w+)(?:\.\w+)*'))
        return re.match(re_pattern+'$', key)

class Icon(object):
    def __init__(self, char, css):
        self.char = char
        self.css = css
