# -*- coding: utf-8 -*-
"""Setup the allura application"""

import logging
from tg import config
import pylons
from paste.registry import Registry

log = logging.getLogger(__name__)
REGISTRY = Registry()

def setup_schema(command, conf, vars):
    """Place any commands to setup allura here"""
    import ming
    import allura

    REGISTRY.prepare()
    REGISTRY.register(pylons.tmpl_context, EmptyClass())
    REGISTRY.register(pylons.app_globals, config['pylons.app_globals'])
    REGISTRY.register(allura.credentials, allura.lib.security.Credentials())
    ming.configure(**conf)
    # Nothing to do
    log.info('setup_schema called')

class EmptyClass(object): pass
