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


'''
This is for making redirects for tickets that we move from SourceForge
to Apache, but could be generalized pretty easily to work for making
any type of redirect (change SF/Apache specifics to commandline arguments)
'''

import argparse
import pymongo


def get_opts():
    parser = argparse.ArgumentParser(
        description='Create MovedTicket records for SourceForge tickets that will be moved to Apache')
    parser.add_argument('-n', help='Neighborhood', default='p')
    parser.add_argument('-p', help='Project', default='allura')
    parser.add_argument('-t', help='Tool mount point', default='tickets')
    parser.add_argument('-f', '--file', help='Path to file with ticket numbers')
    parser.add_argument('--dry-run', help='Run in test mode', action='store_true')
    parser.add_argument('-m', '--mongo', help='Mongo connection string', default='mongodb://localhost:27017/')
    parser.add_argument('--db', help='Database name', default='allura')
    opts = parser.parse_args()
    return opts

opts = get_opts()
ticket_nums = open(opts.file, 'r').read().split()
ticket_nums = [int(num.strip()) for num in ticket_nums]

db = pymongo.MongoClient(opts.mongo)
main_db = db[opts.db]
project_data = db['project-data']

nbhd = main_db.neighborhood.find_one({'url_prefix': '/%s/' % opts.n})
project = main_db.project.find_one({'neighborhood_id': nbhd['_id'], 'shortname': opts.p})
tool = project_data.config.find_one({'project_id': project['_id'], 'options.mount_point': opts.t})

print "Tool id: %s" % tool['_id']
print 'Setting app_config_id to: %s for tickets: %s' % ('moved-to-apache', ticket_nums)

if not opts.dry_run:
    project_data.ticket.update({
        'app_config_id': tool['_id'],
        'ticket_num': {'$in': ticket_nums}
    }, {'$set': {'app_config_id': 'moved-to-apache'}}, multi=True)

print 'Creating MovingTickets for tickets: %s' % ticket_nums

if not opts.dry_run:
    for num in ticket_nums:
        project_data.moved_ticket.insert({
            'app_config_id': tool['_id'],
            'ticket_num': num,
            'moved_to_url': 'https://forge-allura.apache.org/p/allura/tickets/%s' % num,
        })
