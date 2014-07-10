#!/usr/bin/env python
from itertools import tee, izip
import json
import git


filename = "/Users/alexl/Code/allura-backup-2014-07-09-183025/tickets.json"  # Absolute path to exported tickets.json
output = "/Users/alexl/Code/allura-backup-2014-07-09-183025/updated_tickets_100.json"  # Absolute path to the output

gitrepository = "/Users/alexl/Code/allura-git"  # Path to allura repository
g = git.Git(gitrepository)

reviews = ['code-review', 'design-review']
backlog = ['open', 'in-progress', 'validation', 'review', 'blocked']
released = ['closed', 'wontfix', 'invalid']

with open(filename, 'r') as json_file:
    data = json.loads(json_file.read())


def pairwise(iterable):
    """s -> (s0,s1), (s1,s2), (s2, s3), ..."""
    a, b = tee(iterable)
    next(b, None)
    return izip(a, b)


tags = ['asf_release_1.0.0', 'asf_release_1.0.0-RC1', 'asf_release_1.0.1', 'asf_release_1.1.0']

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

del data['milestones']
del data['saved_bins']

updated = []
for ticket in tickets:
    if ticket['ticket_num'] == 6054 or (ticket['status'] != 'deleted' and not ticket['private']):
        if ticket['status'] in reviews:
            ticket['status'] = 'review'

        milestone = ticket_tag.get(ticket['ticket_num'], None)
        if not milestone:
            if ticket['status'] in released:
                milestone = tags[0]
        ticket['custom_fields']['_milestone'] = milestone or 'unreleased'
        if '_size' in ticket['custom_fields'].keys():
            size = ticket['custom_fields']['_size']
            if size:
                ticket['labels'].append("sf-%d" % int(size))
            del ticket['custom_fields']['_size']

        if '_qa' in ticket['custom_fields'].keys():
            ticket['custom_fields']['Reviewer'] = ticket['custom_fields']['_qa']
            del ticket['custom_fields']['_qa']
        updated.append(ticket)

data['tickets'] = updated
data['saved_bins'] = []
data['milestones'] = []
with open(output, 'w') as outfile:
    json.dump(data, outfile)
