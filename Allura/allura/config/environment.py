# -*- coding: utf-8 -*-
"""WSGI environment setup for allura."""

import pylons
import pylons.middleware
import tg
import tg.error
pylons.c = pylons.tmpl_context
pylons.g = pylons.app_globals

from allura.config.app_cfg import base_config

__all__ = ['load_environment']

#Use base_config to setup the environment loader function
load_environment = base_config.make_load_environment()

