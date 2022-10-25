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


from mock import Mock

from allura.lib import helpers as h
from tg import tmpl_context as c
from forgetracker.tracker_main import MilestoneController


def test_unicode_lookup():
    # can't use name= in constructor, that's special attribute for Mock
    milestone = Mock()
    milestone.name = 'Перспектива'
    milestone_field = Mock(milestones=[milestone])
    milestone_field.name = '_milestone'

    app = Mock(globals=Mock(milestone_fields=[milestone_field]))

    with h.push_config(c, app=app):
        root = None
        field = 'milestone'
        # u'Перспектива'
        milestone_urlparam = '%D0%9F%D0%B5%D1%80%D1%81%D0%BF%D0%B5%D0%BA%D1%82%D0%B8%D0%B2%D0%B0'
        mc = MilestoneController(root, field, milestone_urlparam)

    assert mc.milestone  # check that it is found
    assert mc.milestone.name == 'Перспектива'
