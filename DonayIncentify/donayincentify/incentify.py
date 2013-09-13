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

from allura.app import Application
from allura.app import DefaultAdminController
from allura.app import ConfigOption

class IncentifyApp(Application):
    tool_label = 'Incentify'
    tool_description = 'Donay Incentify button for tickets'
    default_mount_label = 'Incentify'
    default_mount_point = 'incentify'
    config_options = Application.config_options + [
            ConfigOption('ShowIncentify', bool, True),
        ]
    template_path_rules = [
            ['>', 'Tickets'],
        ]
