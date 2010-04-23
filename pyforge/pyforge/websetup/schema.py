# -*- coding: utf-8 -*-
"""Setup the pyforge application"""

import logging
from tg import config
import pylons
from pyforge.lib.base import MagicalC, environ

log = logging.getLogger(__name__)

def setup_schema(command, conf, vars):
    """Place any commands to setup pyforge here"""
    import ming
    environ.set_environment({})
    pylons.c._push_object(MagicalC(EmptyClass()))
    ming.configure(**conf)
    from pyforge import model
    # Nothing to do
    log.info('setup_schema called')

class EmptyClass(object): pass
