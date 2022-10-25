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

import mock
from forgetracker.search import get_facets, query_filter_choices


def hit_mock():
    hit = mock.Mock()
    hit.facets = {'facet_fields': {'_milestone_s': ['1.0', 3, '2.0', 2],
                                   'assigned_to_s': ['admin1', 1],
                                   'reported_by_s': ['admin1', 5],
                                   'status_s': ['closed', 1, 'open', 3, 'unread', 1]}}
    reformated = {'_milestone': [('1.0', 3), ('2.0', 2)],
                'assigned_to': [('admin1', 1)],
                'reported_by': [('admin1', 5)],
                'status': [('closed', 1), ('open', 3), ('unread', 1)]}
    return hit, reformated


def test_get_facets():
    hit,expected = hit_mock()
    assert get_facets(hit) == expected


@mock.patch('forgetracker.search.search')
@mock.patch('forgetracker.search.c')
def test_query_filter_choices(c, search):
    hit, expected = hit_mock()
    search.return_value = hit
    result = query_filter_choices()
    params = {'short_timeout': True,
              'fq': ['project_id_s:%s' % c.project._id,
                     'mount_point_s:%s' % c.app.config.options.mount_point,
                     'type_s:Ticket'],
              'rows': 0,
              'facet': 'true',
              'facet.field': ['_milestone_s', 'status_s',
                              'assigned_to_s', 'reported_by_s'],
              'facet.limit': -1,
              'facet.sort': 'index',
              'facet.mincount': 1}
    search.assert_called_once_with(None, **params)
    assert result == expected
