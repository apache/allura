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

import logging

from tg import config
from pylons import app_globals as g

log = logging.getLogger(__name__)


class ImportIdConverter(object):
    '''
    An interface to provide authentication services for Allura.

    To provide a new converter, expose an entry point in setup.py:

        [allura.tickets.import_id_converter]
        mylegacy = foo.bar:LegacyConverter

    Then in your .ini file, set tickets.import_id_converter=mylegacy
    '''

    @classmethod
    def get(cls):
        converter = config.get('tickets.import_id_converter')
        if converter:
            return g.entry_points['allura.tickets.import_id_converter'][converter]()
        return cls()

    def simplify(self, import_id):
        return import_id

    def expand(self, url_part, app_instance):
        return url_part
