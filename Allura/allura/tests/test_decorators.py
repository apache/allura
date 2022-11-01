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
import inspect
from unittest import TestCase
from mock import patch
import random
import gc

from allura.lib.decorators import task, memoize
from alluratest.controller import setup_basic_test, setup_global_objects


class TestTask(TestCase):

    def setup_method(self, method):
        setup_basic_test()

    def test_no_params(self):
        @task
        def func():
            pass
        self.assertTrue(hasattr(func, 'post'))

    def test_with_params(self):
        @task(disable_notifications=True)
        def func():
            pass
        self.assertTrue(hasattr(func, 'post'))

    @patch('allura.lib.decorators.c')
    @patch('allura.model.MonQTask')
    def test_post(self, c, MonQTask):
        @task(disable_notifications=True)
        def func(s, foo=None, **kw):
            pass

        def mock_post(f, args, kw, delay=None):
            self.assertTrue(c.project.notifications_disabled)
            self.assertFalse('delay' in kw)
            self.assertEqual(delay, 1)
            self.assertEqual(kw, dict(foo=2))
            self.assertEqual(args, ('test',))
            self.assertEqual(f, func)

        c.project.notifications_disabled = False
        MonQTask.post.side_effect = mock_post
        func.post('test', foo=2, delay=1)


class TestMemoize:

    def test_function(self):
        @memoize
        def remember_randomy(do_random, foo=None):
            if do_random:
                return random.random()
            else:
                return "constant"

        rand1 = remember_randomy(True)
        rand2 = remember_randomy(True)
        const1 = remember_randomy(False)
        rand_kwargs1 = remember_randomy(True, foo='asdf')
        rand_kwargs2 = remember_randomy(True, foo='xyzzy')
        assert rand1 == rand2
        assert const1 == "constant"
        assert rand1 != rand_kwargs1
        assert rand_kwargs1 != rand_kwargs2

    def test_methods(self):

        class Randomy:
            @memoize
            def randomy(self, do_random):
                if do_random:
                    return random.random()
                else:
                    return "constant"

            @memoize
            def other(self, do_random):
                if do_random:
                    return random.random()
                else:
                    return "constant"

        r = Randomy()
        rand1 = r.randomy(True)
        rand2 = r.randomy(True)
        const1 = r.randomy(False)
        other1 = r.other(True)
        other2 = r.other(True)

        assert rand1 == rand2
        assert const1 == "constant"
        assert rand1 != other1
        assert other1 == other2

        r2 = Randomy()
        r2rand1 = r2.randomy(True)
        r2rand2 = r2.randomy(True)
        r2const1 = r2.randomy(False)
        r2other1 = r2.other(True)
        r2other2 = r2.other(True)

        assert r2rand1 != rand1
        assert r2rand1 == r2rand2
        assert r2other1 != other1
        assert r2other1 == r2other2

    def test_methods_garbage_collection(self):

        class Randomy:
            @memoize
            def randomy(self, do_random):
                if do_random:
                    return random.random()
                else:
                    return "constant"

        r = Randomy()
        rand1 = r.randomy(True)

        for gc_ref in gc.get_referrers(r):
            if inspect.isframe(gc_ref):
                continue
            else:
                raise AssertionError('Unexpected reference to `r` instance: {!r}\n'
                                     '@memoize probably made a reference to it and has created a circular reference loop'.format(gc_ref))
