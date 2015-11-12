# -*- coding: utf-8 -*-

#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

"""Setup the allura application"""

import logging

import activitystream
from tg import config
import pylons
from paste.deploy.converters import asbool
from paste.registry import Registry

from allura.lib import helpers as h

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
    if asbool(conf.get('activitystream.recording.enabled', False)):
        activitystream.configure(**h.convert_bools(conf, prefix='activitystream.'))
    # Nothing to do
    log.info('setup_schema called')


class EmptyClass(object):
    pass
