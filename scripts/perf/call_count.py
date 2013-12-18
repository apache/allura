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
import logging
import random
import string

from pylons import tmpl_context as c
from testfixtures import LogCapture
from mock import patch
import timermiddleware
from ming.odm import ThreadLocalODMSession

from allura import model as M
from allura.lib.helpers import push_config
from allura.tests import TestController
from allura.tests.decorators import patch_middleware_config

from forgewiki import model as WM


def main():
    test = TestController()
    setup(test)
    url = generate_wiki_thread(test)
    ThreadLocalODMSession.close_all()  # make sure ODM sessions won't get re-used
    load_page(test, url)
    test.tearDown()


def setup(test):
    # includes setting up mim
    with patch_middleware_config({'stats.sample_rate': 1,
                                  'stats.debug_line_length': 1000,
                                  }), \
         patch('timermiddleware.log.isEnabledFor', return_value=True):  # can't set this via logging configuration since setUp() will load a logging config and then start using it before we have a good place to tweak it
        test.setUp()

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
    # create 3 posts by 2 users
    with push_config(c, user=M.User.query.get(username='test-admin'),
                        app=app,
                        project=project):
        thread.add_post(text='This is very helpful')
        thread.add_post(text="But it's not **super** helpful")
        with push_config(c, user=M.User.query.get(username='test-user')):
            thread.add_post(text='I disagree')

    ThreadLocalODMSession.flush_all()

    url = '/p/test/wiki/_discuss/thread/{}/'.format(thread._id)
    return url


def load_page(test, url, verbose=False, debug_html=False):

    with LogCapture('stats') as stats, LogCapture('timermiddleware') as calls:
        resp = test.app.get(url, extra_environ=dict(username='*anonymous'))
        print url, resp.status
        if debug_html:
            debug_filename = 'call-{}.html'.format(''.join([random.choice(string.ascii_letters + string.digits) for n in xrange(10)]))
            with open(debug_filename, 'w') as out:
                out.write(resp.body)
            print debug_filename

    if verbose:
        for r in calls.records:
            print r.getMessage()

    for r in stats.records:
        timings = json.loads(r.getMessage())
        print json.dumps(timings['call_counts'])


if __name__ == '__main__':
    main()
