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

import configparser
import logging.config
import os

from paste.deploy import appconfig

from allura import websetup
from . import base


class SetupAppCommand(base.Command):
    # replacement for the old `paster setup-app` from PasteScript
    min_args = 1
    max_args = 1
    usage = '<ini file>'
    summary = 'Set up the application: create initial database objects, neighborhoods, etc.'
    parser = base.Command.standard_parser(verbose=True)

    def command(self):
        config_spec = self.args[0]
        section = 'main'
        if '#' in config_spec:
            config_spec, section = config_spec.split('#', 1)
        config_file = os.path.join(os.getcwd(), config_spec)
        ini_parser = configparser.ConfigParser()
        ini_parser.read([config_file])
        if ini_parser.has_section('loggers'):
            logging.config.fileConfig(config_file, disable_existing_loggers=False)
        conf = appconfig(f'config:{config_file}#{section}')
        websetup.setup_app(self, conf, {})
