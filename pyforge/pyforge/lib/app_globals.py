# -*- coding: utf-8 -*-

"""The application's Globals object"""

__all__ = ['Globals']

import pkg_resources

from tg import config
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
        
