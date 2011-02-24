# -*- coding: utf-8 -*-
"""Setup the allura application"""

import logging
from tg import config
import pylons

log = logging.getLogger(__name__)

def setup_schema(command, conf, vars):
    """Place any commands to setup allura here"""
    import ming
    import allura
    pylons.c._push_object(EmptyClass())
    allura.credentials._push_object(allura.lib.security.Credentials())
    ming.configure(**conf)
    from allura import model
    # Nothing to do
    log.info('setup_schema called')

class EmptyClass(object): pass
