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

from itertools import tee, izip, chain
import json
import git
from collections import Counter

'''
This script is for one-time conversion of Allura's own tickets from SourceForge
host to forge-allura.apache.org hosting

Change path variables here:
'''

filename = "/var/local/allura/tickets.json"  # Absolute path to exported tickets.json
output = "/var/local/allura/updated_tickets.json"  # Absolute path to the output
ticket_list = "/var/local/allura/ticket_ids.list"
top_usernames = "/var/local/allura/top_usernames.list"
gitrepository = "/var/local/allura"  # Path to allura repository
g = git.Git(gitrepository)

reviews = ['code-review', 'design-review']

with open(filename, 'r') as json_file:
    data = json.loads(json_file.read())


def pairwise(iterable):
    """s -> (s0,s1), (s1,s2), (s2, s3), ..."""
    a, b = tee(iterable)
    next(b, None)
    return izip(a, b)


tags = ['asf_release_1.0.0', 'asf_release_1.0.0-RC1', 'asf_release_1.0.1', 'asf_release_1.1.0', 'HEAD']

tag_log = dict()
for tag1, tag2 in pairwise(tags):
    log = g.log('%s...%s' % (tag1, tag2), '--pretty=oneline')
    tag_log[tag2] = log

ticket_tag = dict()
tickets = data.pop('tickets')
for ticket in tickets:
    for key, value in tag_log.iteritems():
        if "[#%s]" % ticket['ticket_num'] in value:
            ticket_tag[ticket['ticket_num']] = key
            continue

data.pop('milestones', None)
data.pop('saved_bins', None)

updated = []
for ticket in tickets:
    if not ticket['private'] or ticket['ticket_num'] == 6054:
        if ticket['status'] in reviews:
            ticket['status'] = 'review'

        milestone = ticket_tag.get(ticket['ticket_num'], None)
        if not milestone:
            if ticket['status'] == 'closed':
                milestone = tags[0]
        ticket['custom_fields']['_milestone'] = milestone if milestone and milestone != 'HEAD' else 'unreleased'
        if '_size' in ticket['custom_fields'].keys():
            size = ticket['custom_fields']['_size']
            if size:
                ticket['labels'].append("sf-%d" % int(size))
            ticket['custom_fields'].pop('_size', None)

        if '_qa' in ticket['custom_fields'].keys():
            ticket['custom_fields']['_reviewer'] = ticket['custom_fields']['_qa']
            ticket['custom_fields'].pop('_qa', None)
        updated.append(ticket)
tags[-1] = 'unreleased'

data['tickets'] = updated

# Remove milestones from the list
custom_fields = filter(lambda d: d.get('name') not in ['_milestone', 'name', '_size', '_qa'], data['custom_fields'])
data['custom_fields'] = custom_fields

milestones = {
    "milestones": [
        dict(name=milestone_name,
             old_name=milestone_name,
             default=False,
             complete=False,
             due_date="",
             description="")
        for milestone_name in tags
    ],
    "name": "_milestone",
    "show_in_search": False,
    "label": "Milestone",
    "type": "milestone",
    "options": ""
}
data['custom_fields'].append(milestones)
data['custom_fields'].append({
    "show_in_search": True,
    "label": "Reviewer",
    "type": "user",
    "options": "",
    "name": "_reviewer"
})
data['milestones'] = milestones
data['saved_bins'] = []

# Count top used usernames

assigned_to = [ticket.get('assigned_to', None) for ticket in updated]
reported_by = [ticket.get('reported_by', None) for ticket in updated]
reviewed_by = [ticket['custom_fields'].get('_reviewer', None) for ticket in updated]

posts = [ticket['discussion_thread']['posts'] for ticket in updated]

post_authors = [post.get('author', None) for post in list(chain(*posts))]

usernames = filter(lambda x: bool(x), chain(assigned_to, reported_by, reviewed_by, post_authors))

top_users = Counter(usernames).most_common(50)

with open(output, 'w') as outfile:
    json.dump(data, outfile, indent=2)

with open(ticket_list, 'w') as outfile:
    outfile.write('\n'.join(sorted([str(ticket['ticket_num']) for ticket in updated])))

with open(top_usernames, 'w') as outfile:
    lines = ["%s - %s" % (username, frequency) for username, frequency in top_users]
    outfile.write('\n'.join(lines))