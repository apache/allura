# -*- coding: utf-8 -*-
"""Setup the pyforge application"""

import logging
from tg import config
import pylons

log = logging.getLogger(__name__)

def setup_schema(command, conf, vars):
    """Place any commands to setup pyforge here"""
    import ming
    pylons.c = EmptyClass()
    ming.configure(**conf)
    from pyforge import model
    # Nothing to do
    log.info('setup_schema called')

class EmptyClass(object): pass
