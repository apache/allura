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
from collections import OrderedDict

import mock

from tg import config
from nose.tools import assert_equals, assert_true
from ming.orm import session

from allura import model as M
from allura.lib import helpers as h
from allura.tests import TestController
from alluratest.controller import setup_trove_categories
from allura.tests import decorators as td


class TestTroveCategory(TestController):

    @mock.patch('allura.model.project.g.post_event')
    def test_events(self, post_event):
        setup_trove_categories()

        # Create event
        cfg = {'trovecategories.enableediting': 'true'}
        with h.push_config(config, **cfg):
            r = self.app.post('/categories/create/', params=dict(categoryname='test'))

        category_id = post_event.call_args[0][1]
        assert_true(isinstance(category_id, int))
        assert_equals(post_event.call_args[0][0], 'trove_category_created')
        category = M.TroveCategory.query.get(trove_cat_id=category_id)

        # Update event
        category.fullname = 'test2'
        session(M.TroveCategory).flush()
        edited_category_id = post_event.call_args[0][1]
        assert_true(isinstance(edited_category_id, int))
        assert_equals(edited_category_id, category_id)
        assert_equals(post_event.call_args[0][0], 'trove_category_updated')

        # Delete event
        M.TroveCategory.delete(category)
        session(M.TroveCategory).flush()
        deleted_category_id = post_event.call_args[0][1]
        assert_true(isinstance(deleted_category_id, int))
        assert_equals(deleted_category_id, category_id)
        assert_equals(post_event.call_args[0][0], 'trove_category_deleted')

    def test_enableediting_setting(self):
        def check_access(username=None, status=None):
            self.app.get('/categories/', status=status,
                         extra_environ=dict(username=username))

        cfg = {'trovecategories.enableediting': 'true'}

        with h.push_config(config, **cfg):
            check_access(username='test-user', status=200)
            check_access(username='root', status=200)

        cfg['trovecategories.enableediting'] = 'false'
        with h.push_config(config, **cfg):
            check_access(username='test-user', status=403)
            check_access(username='root', status=403)

        cfg['trovecategories.enableediting'] = 'admin'
        with h.push_config(config, **cfg):
            check_access(username='test-user', status=403)
            check_access(username='root', status=200)

class TestTroveCategoryController(TestController):
    @td.with_tool('test2', 'admin_main', 'admin')
    def test_trove_hierarchy(self):
        root_parent = M.TroveCategory(fullname="Root", trove_cat_id=1, trove_parent_id=0)
        category_a = M.TroveCategory(fullname="CategoryA", trove_cat_id=2, trove_parent_id=1)
        category_b = M.TroveCategory(fullname="CategoryB", trove_cat_id=3, trove_parent_id=1)
        child_a = M.TroveCategory(fullname="ChildA", trove_cat_id=4, trove_parent_id=2)
        child_b = M.TroveCategory(fullname="ChildB", trove_cat_id=5, trove_parent_id=2)

        session(M.TroveCategory).flush()

        r = self.app.get('/categories/browse')
        tree = r.controller_output['tree']

        expected_data = OrderedDict(
            [('Root', OrderedDict(
                [('CategoryA', OrderedDict([
                    ('ChildA', OrderedDict()),
                    ('ChildB', OrderedDict())
                ])),
                 ('CategoryB', OrderedDict())
                ])
             )]
        )
        assert tree == expected_data

    @td.with_tool('test2', 'admin_main', 'admin')
    def test_trove_empty_hierarchy(self):
        r = self.app.get('/categories/browse')
        tree = r.controller_output['tree']
        assert tree == OrderedDict()

