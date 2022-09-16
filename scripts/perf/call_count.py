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

import argparse
import json
import logging
import random
import string
import csv

from tg import tmpl_context as c
from testfixtures import LogCapture
from mock import patch
from ming.odm import ThreadLocalODMSession

from allura import model as M
from allura.lib.helpers import push_config
from allura.tests import TestController
from allura.tests.decorators import patch_middleware_config

from forgewiki import model as WM


def parse_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter,
        description='Count number of expensive calls (mongo, markdown, etc) for a standard page.\n'
                    'Currently its a _discuss URL with a few posts on it.  This exercises core logic\n'
                    '(project & tool lookup, security, discussion thread, main template, etc) but\n'
                    'intentionally avoids most tool-specific code.')
    parser.add_argument('--verbose', '-v', action='store_true', default=False,
                        help='Show call details.  Note that Timers with debug_each_call=False (like ming\'s Cursor.next) are not displayed in verbose mode (but they are counted).')
    parser.add_argument('--debug-html', action='store_true', default=False,
                        help='Save HTML responses as local files')
    parser.add_argument(
        '--data-file', default='call_counts.csv', type=argparse.FileType('a'),
        help='CSV file that is appended to')
    parser.add_argument('--id', default='',
                        help='An identifier for this run.  Examples:\n'
                             '`git rev-parse --short HEAD` for current hash\n'
                             '`git log -1 --oneline` for hash + message')
    return parser.parse_args()


def main(args):
    test = TestController()
    setup(test)

    url = generate_wiki_thread(test)
    # make sure ODM sessions won't get re-used
    ThreadLocalODMSession.close_all()

    counts = count_page(test, url, verbose=args.verbose,
                        debug_html=args.debug_html)
    print(json.dumps(counts))
    write_csv(counts, args.id, args.data_file)
    test.teardown_method(method)


def setup(test):
    # includes setting up mim
    with patch_middleware_config({'stats.sample_rate': 1,
                                  'stats.debug_line_length': 1000,
                                  }), \
            patch('timermiddleware.log.isEnabledFor', return_value=True):  # can't set this via logging configuration since setUp() will load a logging config and then start using it before we have a good place to tweak it
        test.setup_method(method)

    tmw_log = logging.getLogger('timermiddleware')
    tmw_log.disabled = 0  # gets disabled when .ini file is loaded; dumb.
    tmw_log.setLevel(logging.DEBUG)


def generate_wiki_thread(test):
    # automagically instantiate the app
    test.app.get('/wiki/')

    project = M.Project.query.get(shortname='test')
    app = project.app_instance('wiki')

    page = WM.Page.query.get(app_config_id=app.config._id, title='Home')
    thread = page.discussion_thread
    # create a few posts by a few users
    with push_config(c, user=M.User.query.get(username='test-admin'),
                     app=app,
                     project=project):
        thread.add_post(text='This is very helpful')
        thread.add_post(text="But it's not **super** helpful")
        with push_config(c, user=M.User.query.get(username='test-user')):
            thread.add_post(text='I disagree')
        with push_config(c, user=M.User.query.get(username='test-user-1')):
            thread.add_post(text='But what about foo?')

    ThreadLocalODMSession.flush_all()

    url = f'/p/test/wiki/_discuss/thread/{thread._id}/'
    return url


def count_page(test, url, verbose=False, debug_html=False):

    with LogCapture('stats') as stats, LogCapture('timermiddleware') as calls:
        resp = test.app.get(url, extra_environ=dict(username='*anonymous'))
        print(url, resp.status)
        if debug_html:
            debug_filename = 'call-{}.html'.format(''.join([random.choice(string.ascii_letters + string.digits)
                                                   for n in range(10)]))
            with open(debug_filename, 'w') as out:
                out.write(resp.body)
            print(debug_filename)

    if verbose:
        for r in calls.records:
            print(r.getMessage())

    assert len(stats.records) == 1
    timings = json.loads(stats.records[0].getMessage())
    # total is always 1, which is misleading
    del timings['call_counts']['total']
    return timings['call_counts']


def write_csv(counts, id, data_file):
    cols = sorted(counts.keys())
    row = counts
    if id:
        cols = ['id'] + cols
        row = dict(counts, id=id)
    csv_out = csv.DictWriter(data_file, cols)
    if data_file.tell() == 0:
        csv_out.writeheader()
    csv_out.writerow(row)
    data_file.close()


if __name__ == '__main__':
    main(parse_args())
