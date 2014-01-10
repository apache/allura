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

from unittest import TestCase

from mock import patch

from allura.lib.decorators import task


class TestTask(TestCase):

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
