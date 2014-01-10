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

import logging
import string
import os
from urllib import urlencode

import bson
from tg import expose, session, flash, redirect, validate, config
from tg.decorators import with_trailing_slash
from pylons import tmpl_context as c, app_globals as g
from pylons import request, response
from string import digits, lowercase

from allura.lib.security import require_authenticated
from allura import model as M
from allura.lib.decorators import require_post
from allura.controllers import BaseController
from allura.lib.widgets import forms
from allura.model import TroveCategory


class F(object):
    remove_category_form = forms.RemoveTroveCategoryForm()
    add_category_form = forms.AddTroveCategoryForm()


class TroveCategoryController(BaseController):

    @expose()
    def _lookup(self, catshortname, *remainder):
        cat = M.TroveCategory.query.get(shortname=catshortname)
        return TroveCategoryController(category=cat), remainder

    def __init__(self, category=None):
        self.category = category
        super(TroveCategoryController, self).__init__()

    @expose('jinja:allura:templates/trovecategories.html')
    def index(self, **kw):
        require_authenticated()

        if self.category:
            selected_cat = self.category
            l = self.category.subcategories
            hierarchy = []
            temp_cat = self.category.parent_category
            while temp_cat:
                hierarchy = [temp_cat] + hierarchy
                temp_cat = temp_cat.parent_category
        else:
            l = M.TroveCategory.query.find(dict(trove_parent_id=0)).all()
            selected_cat = None
            hierarchy = []
        return dict(
            categories=l,
            selected_cat=selected_cat,
            hierarchy=hierarchy)

    @expose()
    @require_post()
    @validate(F.add_category_form, error_handler=index)
    def create(self, **kw):
        require_authenticated()

        name = kw.get('categoryname')
        upper_id = int(kw.get('uppercategory_id', 0))

        upper = M.TroveCategory.query.get(trove_cat_id=upper_id)
        if upper_id == 0:
            path = name
            show_as_skill = True
        elif upper is None:
            flash('Invalid upper category.', "error")
            redirect('/categories')
            return
        else:
            path = upper.fullpath + " :: " + name
            show_as_skill = upper.show_as_skill

        newid = max(
            [el.trove_cat_id for el in M.TroveCategory.query.find()]) + 1
        shortname = name.replace(" ", "_").lower()
        shortname = ''.join([(c if (c in digits or c in lowercase) else "_")
                             for c in shortname])

        oldcat = M.TroveCategory.query.get(shortname=shortname)
        if oldcat:
            flash('Category "%s" already exists.' % name, "error")
        else:
            category = M.TroveCategory(
                trove_cat_id=newid,
                trove_parent_id=upper_id,
                fullname=name,
                shortname=shortname,
                fullpath=path,
                show_as_skill=show_as_skill)
            if category:
                flash('Category "%s" successfully created.' % name)
            else:
                flash('An error occured while crearing the category.', "error")
        if upper:
            redirect('/categories/%s' % upper.shortname)
        else:
            redirect('/categories')

    @expose()
    @require_post()
    @validate(F.remove_category_form, error_handler=index)
    def remove(self, **kw):
        require_authenticated()

        cat = M.TroveCategory.query.get(trove_cat_id=int(kw['categoryid']))
        if cat.trove_parent_id:
            parent = M.TroveCategory.query.get(
                trove_cat_id=cat.trove_parent_id)
            redirecturl = '/categories/%s' % parent.shortname
        else:
            redirecturl = '/categories'
        if len(cat.subcategories) > 0:
            m = "This category contains at least one sub-category, "
            m = m + "therefore it can't be removed."
            flash(m, "error")
            redirect(redirecturl)
            return

        if M.User.withskill(cat).count() > 0:
            m = "This category is used as a skill by at least a user, "
            m = m + "therefore it can't be removed."
            flash(m, "error")
            redirect(redirecturl)
            return

        if M.Project.query.get(trove_root_database=cat._id):
            m = "This category is used as a database by at least a project, "
            m = m + "therefore it can't be removed."
            flash(m, "error")
            redirect(redirecturl)
            return

        if M.Project.query.get(trove_developmentstatus=cat._id):
            m = "This category is used as development status by at least a "
            m = m + "project, therefore it can't be removed."
            flash(m, "error")
            redirect(redirecturl)
            return

        if M.Project.query.get(trove_audience=cat._id):
            m = "This category is used as intended audience by at least a "
            m = m + "project, therefore it can't be removed."
            flash(m, "error")
            redirect(redirecturl)
            return

        if M.Project.query.get(trove_license=cat._id):
            m = "This category is used as a license by at least a "
            m = m + "project, therefore it can't be removed."
            flash(m, "error")
            redirect(redirecturl)
            return

        if M.Project.query.get(trove_os=cat._id):
            m = "This category is used as operating system by at least a "
            m = m + "project, therefore it can't be removed."
            flash(m, "error")
            redirect(redirecturl)
            return

        if M.Project.query.get(trove_language=cat._id):
            m = "This category is used as programming language by at least a "
            m = m + "project, therefore it can't be removed."
            flash(m, "error")
            redirect(redirecturl)
            return

        if M.Project.query.get(trove_topic=cat._id):
            m = "This category is used as a topic by at least a "
            m = m + "project, therefore it can't be removed."
            flash(m, "error")
            redirect(redirecturl)
            return

        if M.Project.query.get(trove_natlanguage=cat._id):
            m = "This category is used as a natural language by at least a "
            m = m + "project, therefore it can't be removed."
            flash(m, "error")
            redirect(redirecturl)
            return

        if M.Project.query.get(trove_environment=cat._id):
            m = "This category is used as an environment by at least a "
            m = m + "project, therefore it can't be removed."
            flash(m, "error")
            redirect(redirecturl)
            return

        M.TroveCategory.delete(cat)

        flash('Category removed.')
        redirect(redirecturl)
