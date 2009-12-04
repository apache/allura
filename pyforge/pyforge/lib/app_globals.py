# -*- coding: utf-8 -*-

"""The application's Globals object"""

__all__ = ['Globals']

import pkg_resources

from tg import config
from pylons import c
import paste.deploy.converters
import pysolr
from carrot.connection import BrokerConnection
from carrot.messaging import Publisher

from pyforge import model as M

class Globals(object):
    """Container for objects available throughout the life of the application.

    One instance of Globals is created during application initialization and
    is available during requests via the 'app_globals' variable.

    """

    def __init__(self):
        """Do nothing, by default."""
        self.pyforge_templates = pkg_resources.resource_filename('pyforge', 'templates')
        self.solr_server = config['solr.server']
        self.solr =  pysolr.Solr(self.solr_server)
        self.use_queue = paste.deploy.converters.asbool(
            config.get('use_queue', False))
        self.conn = BrokerConnection(
            hostname=config.get('amqp.hostname', 'localhost'),
            port=config.get('amqp.port', 5672),
            userid=config.get('amqp.userid', 'testuser'),
            password=config.get('amqp.password', 'testpw'),
            virtual_host=config.get('amqp.vhost', 'testvhost'))
        self.publisher = dict(
            audit=Publisher(connection=self.conn, exchange='audit', auto_declare=False),
            react=Publisher(connection=self.conn, exchange='react', auto_declare=False))
        
    def app_static(self, resource, app=None):
        app = app or c.app
        return ''.join(
            [ config['static_root'],
              app.config.plugin_name,
              '/',
              resource ])

    def set_project(self, pid):
        c.project = M.Project.m.get(_id=pid + '/')

    def set_app(self, name):
        c.app = c.project.app_instance(name)

    def publish(self, xn, key, message, **kw):
        project = getattr(c, 'project', None)
        app = getattr(c, 'app', None)
        if project:
            message.setdefault('project_id', project._id)
        if app:
            message.setdefault('mount_point', app.config.options.mount_point)
        self.publisher[xn].send(message, routing_key=key, **kw)
