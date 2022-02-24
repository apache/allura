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
import tg
from tg import config
from paste.deploy.converters import asbool
from tg.support.registry import Registry
from tg.wsgiapp import RequestLocals

from allura.lib import helpers as h
from allura.lib.utils import configure_ming

log = logging.getLogger(__name__)
REGISTRY = Registry()


def setup_schema(command, conf, vars):
    """Place any commands to setup allura here"""
    import ming
    import allura

    # turbogears has its own special magic wired up for its globals, can't use a regular Registry
    tgl = RequestLocals()
    tgl.tmpl_context = EmptyClass()
    tgl.app_globals = config['tg.app_globals']
    tg.request_local.context._push_object(tgl)

    REGISTRY.prepare()
    REGISTRY.register(allura.credentials, allura.lib.security.Credentials())

    configure_ming(conf)
    if asbool(conf.get('activitystream.recording.enabled', False)):
        activitystream.configure(**h.convert_bools(conf, prefix='activitystream.'))
    # Nothing to do
    log.info('setup_schema called')


class EmptyClass:
    pass
