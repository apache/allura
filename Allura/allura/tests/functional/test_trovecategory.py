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
from bs4 import BeautifulSoup
import mock

from tg import config
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
        assert isinstance(category_id, int)
        assert post_event.call_args[0][0] == 'trove_category_created'
        category = M.TroveCategory.query.get(trove_cat_id=category_id)

        # Update event
        category.fullname = 'test2'
        session(M.TroveCategory).flush()
        edited_category_id = post_event.call_args[0][1]
        assert isinstance(edited_category_id, int)
        assert edited_category_id == category_id
        assert post_event.call_args[0][0] == 'trove_category_updated'

        # Delete event
        M.TroveCategory.delete(category)
        session(M.TroveCategory).flush()
        deleted_category_id = post_event.call_args[0][1]
        assert isinstance(deleted_category_id, int)
        assert deleted_category_id == category_id
        assert post_event.call_args[0][0] == 'trove_category_deleted'

    def test_enableediting_setting(self):
        def check_access(username=None, status=None):
            self.app.get('/categories/', status=status,
                         extra_environ=dict(username=str(username)))

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
    def create_some_cats(self):
        root_parent = M.TroveCategory(fullname="Root", trove_cat_id=1, trove_parent_id=0)
        category_a = M.TroveCategory(fullname="CategoryA", trove_cat_id=2, trove_parent_id=1)
        category_b = M.TroveCategory(fullname="CategoryB", trove_cat_id=3, trove_parent_id=1)
        child_a = M.TroveCategory(fullname="ChildA", trove_cat_id=4, trove_parent_id=2)
        child_b = M.TroveCategory(fullname="ChildB", trove_cat_id=5, trove_parent_id=2)

    def test_root(self):
        self.create_some_cats()
        session(M.TroveCategory).flush()
        r = self.app.get('/categories/')
        assert '<a href="/categories/1">Root</a>' in r

    def test_subcat(self):
        self.create_some_cats()
        session(M.TroveCategory).flush()
        r = self.app.get('/categories/1')
        assert '<a href="/categories/2">CategoryA</a>' in r
        assert '<a href="/categories/3">CategoryB</a>' in r

    @td.with_tool('test2', 'admin_main', 'admin')
    def test_trove_hierarchy(self):
        self.create_some_cats()
        session(M.TroveCategory).flush()

        r = self.app.get('/categories/browse')
        rendered_tree = r.html.find('div', {'id': 'content_base'}).find('div').find('div').find('ul')
        expected = BeautifulSoup("""
        <ul>
            <li>Root</li>
            <ul>
                <li>CategoryA</li>
                <ul>
                    <li>ChildA</li>
                    <li>ChildB</li>
                </ul>
                <li>CategoryB</li>
            </ul>
        </ul>
        """.strip(), 'html.parser')
        assert str(expected) == str(rendered_tree)

    @td.with_tool('test2', 'admin_main', 'admin')
    def test_trove_empty_hierarchy(self):
        r = self.app.get('/categories/browse')
        rendered_tree = r.html.find('div', {'id': 'content_base'}).find('div').find('div').find('ul')
        expected = BeautifulSoup("""
        <ul>
        </ul>
        """.strip(), 'html.parser')
        assert str(expected) == str(rendered_tree)

    def test_delete(self):
        self.create_some_cats()
        session(M.TroveCategory).flush()
        assert 5 == M.TroveCategory.query.find().count()

        r = self.app.get('/categories/1')
        form = r.forms[0]
        r = form.submit()
        assert ("This category contains at least one sub-category, therefore it can't be removed" in
                  self.webflash(r))

        r = self.app.get('/categories/2')
        form = r.forms[0]
        r = form.submit()
        assert "Category removed" in self.webflash(r)
        assert 4 == M.TroveCategory.query.find().count()

    def test_create_parent(self):
        self.create_some_cats()
        session(M.TroveCategory).flush()
        r = self.app.get('/categories/')

        form = r.forms[1]
        form['categoryname'].value = "New Category"
        form.submit()

        possible = M.TroveCategory.query.find(dict(fullname='New Category')).all()
        assert len(possible) == 1
        assert possible[0].fullname == 'New Category'
        assert possible[0].shortname == 'new-category'

    def test_create_child(self):
        self.create_some_cats()
        session(M.TroveCategory).flush()
        r = self.app.get('/categories/2')

        form = r.forms[2]
        form['categoryname'].value = "New Child"
        form.submit()

        possible =M.TroveCategory.query.find(dict(fullname='New Child')).all()
        assert len(possible) == 1
        assert possible[0].fullname == 'New Child'
        assert possible[0].shortname == 'new-child'
        assert possible[0].trove_parent_id == 2

        # test slugify with periods. the relevant form becomes the third, after a child has been created above.
        r = self.app.get('/categories/2')
        form = r.forms[3]
        form['categoryname'].value = "New Child.io"
        form.submit()
        possible = M.TroveCategory.query.find(dict(fullname='New Child.io')).all()
        assert possible[0].shortname == 'new-child.io'

    def test_create_child_bad_upper(self):
        self.create_some_cats()
        session(M.TroveCategory).flush()
        r = self.app.get('/categories/2')

        form = r.forms[2]
        form['categoryname'].value = "New Child"
        form['uppercategory_id'].value = "541561615"
        r = form.submit().follow()

        assert 'Invalid upper category' in r.text
