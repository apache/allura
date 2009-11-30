# -*- coding: utf-8 -*-

"""The application's Globals object"""

__all__ = ['Globals']

import pkg_resources

from tg import config
from pylons import c
import pysolr

from pyforge import model as M

class Globals(object):
    """Container for objects available throughout the life of the application.

    One instance of Globals is created during application initialization and
    is available during requests via the 'app_globals' variable.

    """

    def __init__(self):
        """Do nothing, by default."""
        self.pyforge_templates = pkg_resources.resource_filename('pyforge', 'templates')
        self.solr =  pysolr.Solr(config['solr.server'])
        
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
