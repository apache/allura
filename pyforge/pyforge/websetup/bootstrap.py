# -*- coding: utf-8 -*-
"""Setup the pyforge application"""

import logging
from tg import config
from pyforge import model

import transaction


def bootstrap(command, conf, vars):
    """Place any commands to setup pyforge here"""

    # <websetup.bootstrap.before.auth

    # <websetup.bootstrap.after.auth>
