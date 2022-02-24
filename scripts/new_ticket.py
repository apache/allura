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

import sys
import argparse
import requests
from pprint import pprint


def get_parser():
    parser = argparse.ArgumentParser(
        description='Post a new ticket using the API')
    parser.add_argument('project', help='Project shortname')
    parser.add_argument('mount_point', help='Tracker mount point')
    parser.add_argument('-H', '--host', default='sourceforge.net', help='Base domain')
    return parser


def get_opts():
    opts = get_parser().parse_args()
    opts.url = 'https://{}/rest/p/{}/{}/new'.format(opts.host,
                                                    opts.project, opts.mount_point)
    return opts


if __name__ == '__main__':
    opts = get_opts()
    access_token = input('Access (bearer) token: ')
    summary = input('Summary: ')
    print('Description (C-d to end):')
    print('-----------------------------------------------')
    description = sys.stdin.read()
    print('-----------------------------------------------')

    r = requests.post(opts.url, params={
        'access_token': access_token,
        'ticket_form.summary': summary,
        'ticket_form.description': description,
    })
    if r.status_code == 200:
        print('Ticket created at: %s' % r.url)
        pprint(r.json())
    else:
        print(f'Error [{r.status_code}]:\n{r.text}')
