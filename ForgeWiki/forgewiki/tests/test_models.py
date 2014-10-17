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

from allura.tests import TestController
from allura.tests import decorators as td
from alluratest.controller import setup_global_objects

from forgewiki.model import Page


class TestPageSnapshots(TestController):

    @td.with_wiki
    def test_version_race(self):
        # threads must not throw DuplicateKeyError
        # details https://sourceforge.net/p/allura/tickets/7647/
        import time
        import random
        from threading import Thread

        page = Page.upsert('test-page')
        page.commit()

        def run(n):
            setup_global_objects()
            for i in range(10):
                page = Page.query.get(title='test-page')
                page.text = 'Test Page %s.%s' % (n, i)
                time.sleep(random.random())
                page.commit()

        t1 = Thread(target=lambda: run(1))
        t2 = Thread(target=lambda: run(2))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        page = Page.query.get(title='test-page')
        # 10 changes by each thread + initial upsert
        assert page.history().count() == 21, page.history().count()
