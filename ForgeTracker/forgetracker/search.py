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
from tg import tmpl_context as c

from allura.lib.search import search
import six


FACET_PARAMS = {
    'facet': 'true',
    'facet.field': ['_milestone_s', 'status_s', 'assigned_to_s', 'reported_by_s'],
    'facet.limit': -1,
    'facet.sort': 'index',
    'facet.mincount': 1,
}


def query_filter_choices(arg=None, fq=[]):
    """
    Makes solr query and returns facets for tickets.

    :param arg: solr query, string
    """
    params = {
        'short_timeout': True,
        'fq': [
            'project_id_s:%s' % c.project._id,
            'mount_point_s:%s' % c.app.config.options.mount_point,
            'type_s:Ticket',
            ] + fq,
        'rows': 0,
    }
    params.update(FACET_PARAMS)
    result = search(arg, **params)
    return get_facets(result)


def get_facets(solr_hit):
    """
    Filter and reshape facets for given solr result.

    :param solr_hit: solr result instance.
    """
    result = {}
    if solr_hit is not None:
        for facet_name, values in solr_hit.facets['facet_fields'].items():
            field_name = facet_name.rsplit('_s', 1)[0]
            values = [(values[i], values[i+1]) for i in range(0, len(values), 2)]
            result[field_name] = values
    return result
