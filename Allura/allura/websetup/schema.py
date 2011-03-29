# -*- coding: utf-8 -*-
"""Setup the allura application"""

import logging
from tg import config, c, g
from paste.registry import Registry

log = logging.getLogger(__name__)
REGISTRY = Registry()

def setup_schema(command, conf, vars):
    """Place any commands to setup allura here"""
    import ming
    import allura.lib.app_globals

    REGISTRY.prepare()
    REGISTRY.register(config, conf)
    REGISTRY.register(g, allura.lib.app_globals.Globals())
    REGISTRY.register(c, EmptyClass())
    REGISTRY.register(allura.credentials, allura.lib.security.Credentials())
    ming.configure(**conf)
    from allura import model
    # Nothing to do
    log.info('setup_schema called')

class EmptyClass(object): pass
