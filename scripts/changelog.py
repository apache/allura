#!/usr/bin/env python

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

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import
import sys
import re
import git
import requests
from datetime import datetime


CHANGELOG = 'CHANGES'
API_URL = 'https://forge-allura.apache.org/rest/p/allura/tickets/search?limit=1000&q=ticket_num:({0})'


def main():
    from_ref, to_ref, version = get_versions()
    tickets, changes_without_tickets = get_tickets(from_ref, to_ref)
    summaries = get_ticket_summaries(tickets)
    print_changelog(version, summaries, changes_without_tickets)


def get_versions():
    return sys.argv[1], sys.argv[2], sys.argv[3]


def get_tickets(from_ref, to_ref):
    repo = git.Repo('.')
    ticket_nums = set()
    changes_without_tickets = []
    ref_spec = '..'.join([from_ref, to_ref])
    for commit in repo.iter_commits(ref_spec):
        match = re.match(r'\s*\[#(\d+)\]', commit.summary)
        if match:
            ticket_nums.add(match.group(1))
        else:
            changes_without_tickets.append(commit.summary)
    return list(ticket_nums), changes_without_tickets


def get_ticket_summaries(tickets):
    summaries = {}
    r = requests.get(API_URL.format(' '.join(tickets)))
    if r.status_code != 200:
        raise ValueError('Unexpected response code: {0}'.format(r.status_code))
    for ticket in r.json()['tickets']:
        summaries[ticket['ticket_num']] = ticket['summary']
    return summaries


def print_changelog(version, summaries, changes_without_tickets):
    print('Version {version}  ({date})\n'.format(**{
        'version': version,
        'date': datetime.utcnow().strftime('%B %Y'),
    }))
    for ticket in sorted(summaries.keys()):
        print(" * [#{0}] {1}".format(ticket, summaries[ticket].encode('utf-8')))
    for change in changes_without_tickets:
        print(" * {}".format(change.encode('utf-8')))

if __name__ == '__main__':
    main()
