#!/bin/env python

import os
import argparse
import requests

def get_opts():
    parser = argparse.ArgumentParser(description='Initiate and download a project export using the API')
    parser.add_argument('project', help='Project shortname')
    parser.add_argument('tools', nargs='+', help='Tool mount-points to export')
    parser.add_argument('-H', '--host', default='sourceforge.net', help='Host name')
    opts = parser.parse_args()
    opts.url = 'https://{0}/rest/p/{1}/admin/'.format(opts.host, opts.project)
    return opts

opts = get_opts()
access_token = raw_input('Access (bearer) token: ')
username = raw_input('Username: ')

r = requests.post(opts.url+'export', params={
        'access_token': access_token,
        'tools': opts.tools,
    })
assert r.status_code != 400, 'Invalid or missing tool mount-point'
assert r.status_code != 503, 'Export already in progress'
assert r.status_code == 200, 'Error [{0}]:\n{1}'.format(r.status_code, r.text)

filename = r.json()['filename']

print "Waiting for {0} to be ready...".format(filename)
while True:
    r = requests.get(opts.url+'export_status', params={'access_token': access_token})
    assert r.status_code == 200, 'Error [{0}]:\n{1}'.format(r.status_code, r.text)
    if r.json()['status'] == 'ready':
        break

print "Copying {0}...".format(filename)
os.execv('/bin/env', [
        'scp',
        '{username}@web.sourceforge.net:/home/project-exports/{project}/{filename}'.format(
            username=username,
            project=opts.project,
            filename=filename
        ),
        '.',
    ])
