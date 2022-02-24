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

import json
from datetime import datetime
import argparse
import sys


parser = argparse.ArgumentParser(description='Parse TimerMiddleware json lines (e.g. stats.log), filter them, output tab-delimited')
parser.add_argument('-f', '--filter-category', type=str, nargs='+', metavar='CAT',
                    help='e.g. tickets, or discussion, etc')
parser.add_argument('-t', '--timings', type=str, nargs='+', metavar='TIMING', required=True,
                    help='e.g. total ming mongo sidebar jinja ...')
parser.add_argument('-i', '--input-file', type=argparse.FileType('r'), nargs='?', default=sys.stdin,
                    help='Filename, or use stdin by default')
args = parser.parse_args()

timings = []
for line in args.input_file:
    data = json.loads(line)
    try:
        typ = data['message']['request_category']
    except KeyError:
        #print 'No category', data['message']['url']
        pass
    if args.filter_category and typ not in args.filter_category:
        continue

    time = datetime.strptime(data['time'], '%Y-%m-%d %H:%M:%S,%f')
    output = [time]
    for timing in args.timings:
        output.append(data['message']['timings'].get(timing, 0))
    timings.append(output)

timings.sort()  # in case of multiple input files

print('\t'.join(['Time'] + args.timings))
for t in timings:
    print('\t'.join(map(str, t)))
