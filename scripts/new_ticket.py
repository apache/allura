#!/usr/bin/env python

import sys
import argparse
import requests
from pprint import pprint

def get_opts():
    parser = argparse.ArgumentParser(description='Post a new ticket using the API')
    parser.add_argument('project', help='Project shortname')
    parser.add_argument('mount_point', help='Tracker mount point')
    parser.add_argument('-H', '--host', default='sourceforge.net')
    opts = parser.parse_args()
    opts.url = 'https://{}/rest/p/{}/{}/new'.format(opts.host, opts.project, opts.mount_point)
    return opts

opts = get_opts()
access_token = raw_input('Access (bearer) token: ')
summary = raw_input('Summary: ')
print 'Description (C-d to end):'
print '-----------------------------------------------'
description = sys.stdin.read()
print '-----------------------------------------------'

r = requests.post(opts.url, params={
        'access_token': access_token,
        'ticket_form.summary': summary,
        'ticket_form.description': description,
    })
if r.status_code == 200:
    print 'Ticket created at: %s' % r.url
    pprint(r.json())
else:
    print 'Error [%s]:\n%s' % (r.status_code, r.text)
