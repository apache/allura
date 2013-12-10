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

from pylons import tmpl_context as c

from allura.lib.search import search


def choices_for_filter():
    params = {
        'short_timeout': True,
        'fq': [
            'project_id_s:%s' % c.project._id,
            'mount_point_s:%s' % c.app.config.options.mount_point
            ],
        'rows': 0,
        'facet': 'true',
        'facet.field': ['milestone_s', 'status_s', 'assigned_to_s', 'reported_by_s'],
        'facet.limit': -1,
        'facet.sort': 'index',
        'facet.mincount': 1,
    }
    result = search(None, **params)
    def reformat(field):
        name, val = field
        name = name[:-2] if name != 'milestone_s' else '_milestone'
        new_val = []
        for i in range(0, len(val), 2):
            new_val.append((val[i], val[i+1]))
        return name, new_val
    return dict(map(reformat, result.facets['facet_fields'].iteritems()))
