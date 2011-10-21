# -*- coding: utf-8 -*-
"""WSGI environment setup for allura."""

import pylons
pylons.c = pylons.tmpl_context
pylons.g = pylons.app_globals
import tg
import tg.error
import pylons.middleware

from allura.config.app_cfg import base_config

__all__ = ['load_environment']

#Use base_config to setup the environment loader function
load_environment = base_config.make_load_environment()

