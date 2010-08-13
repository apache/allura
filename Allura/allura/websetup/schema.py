# -*- coding: utf-8 -*-
"""Setup the allura application"""

import logging
from tg import config
import pylons
from allura.lib.custom_middleware import MagicalC, environ

log = logging.getLogger(__name__)

def setup_schema(command, conf, vars):
    """Place any commands to setup allura here"""
    import ming
    environ.set_environment({})
    pylons.c._push_object(MagicalC(EmptyClass(), environ))
    ming.configure(**conf)
    from allura import model
    # Nothing to do
    log.info('setup_schema called')

class EmptyClass(object): pass
