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

import os
import logging

import pkg_resources

from allura.app import Application
from allura.lib.helpers import iter_entry_points

log = logging.getLogger(__name__)

def register_ew_resources(manager):
    manager.register_directory(
        'js', pkg_resources.resource_filename('allura', 'lib/widgets/resources/js'))
    manager.register_directory(
        'css', pkg_resources.resource_filename('allura', 'lib/widgets/resources/css'))
    manager.register_directory(
        'allura', pkg_resources.resource_filename('allura', 'public/nf'))
    for ep in iter_entry_points('allura'):
        try:
            # Allow derived tools to "inherit" static resources from a parent.
            module_name = ep.module_name
            resource_path = os.path.join('nf', ep.name.lower())
            if not pkg_resources.resource_exists(module_name, resource_path):
                for cls in [c for c in ep.load().__mro__[1:]
                        if issubclass(c, Application)]:
                    module_name = cls.__module__
                    if pkg_resources.resource_exists(module_name, resource_path):
                        break
                else:
                    continue

            manager.register_directory(
                'tool/%s' % ep.name.lower(),
                pkg_resources.resource_filename(
                    module_name, resource_path))
        except ImportError:
            log.warning('Cannot import entry point %s', ep)
            raise
    for ep in iter_entry_points('allura.theme'):
        try:
            theme = ep.load()
            theme.register_ew_resources(manager, ep.name)
        except ImportError:
            log.warning('Cannot import entry point %s', ep)
            raise
