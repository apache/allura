# -*- coding: utf-8 -*-
"""Setup the allura application"""

import logging

__all__ = ['setup_app']

log = logging.getLogger(__name__)

from schema import setup_schema
import bootstrap

from paste.script.appinstall import Installer

def setup_app(command, conf, vars):
    """Place any commands to setup allura here"""
    setup_schema(command, conf, vars)
    bootstrap.bootstrap(command, conf, vars)
