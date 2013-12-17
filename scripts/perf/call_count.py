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
from pprint import pprint

from pylons import tmpl_context as c
from testfixtures import LogCapture

from allura import model as M
from allura.lib.helpers import push_config
from allura.tests import TestController
from allura.tests.decorators import patch_middleware_config

from forgewiki import model as WM


def main():
    test = TestController()
    setup(test)
    url = generate_wiki_thread(test)
    load_page(test, url)
    load_page(test, url)
    load_page(test, url)
    test.tearDown()


def setup(test):
    # includes setting up mim
    with patch_middleware_config({'stats.sample_rate': 1}):
       test.setUp()


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

    url = '/p/test/wiki/_discuss/thread/{}/'.format(thread._id)
    return url


def load_page(test, url):
    with LogCapture('stats') as l:
        print url, test.app.get(url, extra_environ=dict(username='*anonymous')).status
    for r in l.records:
        timings = json.loads(r.message)
        print json.dumps(timings['call_counts'])

if __name__ == '__main__':
    main()
