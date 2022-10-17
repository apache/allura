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

from tg import tmpl_context as c, app_globals as g

from alluratest.controller import setup_basic_test, setup_global_objects
from allura import model as M
from allura.lib import security
from allura.lib import helpers as h


def setup_module(module):
    setup_basic_test()
    setup_global_objects()
    h.set_context('test', neighborhood='Projects')
    c.project.install_app('blog', 'blog')
    g.set_app('blog')


def test_role_assignments():
    admin = M.User.by_username('test-admin')
    user = M.User.by_username('test-user')
    anon = M.User.anonymous()

    def check_access(perm):
        pred = security.has_access(c.app, perm)
        return pred(user=admin), pred(user=user), pred(user=anon)
    assert check_access('configure') == (True, False, False)
    assert check_access('read') == (True, True, True)
    assert check_access('write') == (True, False, False)
    assert check_access('unmoderated_post') == (True, True, False)
    assert check_access('post') == (True, True, False)
    assert check_access('moderate') == (True, False, False)
    assert check_access('admin') == (True, False, False)
