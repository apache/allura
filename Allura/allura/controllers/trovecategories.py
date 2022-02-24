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
import re
from collections import OrderedDict

from tg import expose, flash, redirect, validate, config
from tg import tmpl_context as c
from tg.decorators import without_trailing_slash
from webob.exc import HTTPForbidden, HTTPNotFound
from tg import app_globals as g

from allura import model as M
from allura.controllers import BaseController
from allura.lib import helpers as h
from allura.lib.decorators import require_post
from allura.lib.security import require_authenticated, require_site_admin
from allura.lib.widgets import forms
from allura.lib.plugin import SiteAdminExtension
from allura.app import SitemapEntry
import six


class F:
    remove_category_form = forms.RemoveTroveCategoryForm()
    add_category_form = forms.AddTroveCategoryForm()


class TroveAdminException(Exception):
    def __init__(self, flash_args, redir_params='', upper=None):
        super().__init__()

        self.flash_args = flash_args
        self.redir_params = redir_params
        self.upper = upper


class TroveCategoryController(BaseController):
    @expose()
    def _lookup(self, trove_cat_id, *remainder):
        cat = M.TroveCategory.query.get(trove_cat_id=int(trove_cat_id))
        if not cat:
            raise HTTPNotFound
        return TroveCategoryController(category=cat), remainder

    def _check_security(self):
        require_authenticated()

        enable_editing = config.get('trovecategories.enableediting', 'false')
        if enable_editing == 'admin':
            require_site_admin(c.user)
        elif enable_editing != 'true':
            raise HTTPForbidden()

    def __init__(self, category=None):
        self.category = category
        super().__init__()

    @expose('jinja:allura:templates/trovecategories.html')
    def index(self, **kw):
        if self.category:
            selected_cat = self.category
            l = self.category.subcategories
            hierarchy = []
            temp_cat = self.category.parent_category
            while temp_cat:
                hierarchy = [temp_cat] + hierarchy
                temp_cat = temp_cat.parent_category
        else:
            l = M.TroveCategory.query.find(dict(trove_parent_id=0)).sort('fullname').all()
            selected_cat = None
            hierarchy = []
        return dict(
            categories=l,
            selected_cat=selected_cat,
            hierarchy=hierarchy,
            kw=kw)

    def generate_category(self, category):
        if not category:
            return ()

        children = {
            key: value
            for (key, value) in
            (self.generate_category(child) for child in category.subcategories)
        }

        return category.fullname, OrderedDict(sorted(children.items()))

    @without_trailing_slash
    @expose('jinja:allura:templates/browse_trove_categories.html')
    def browse(self):
        parent_categories = M.TroveCategory.query.find(dict(trove_parent_id=0)).all()
        tree = {
            key: value
            for (key, value) in
            (self.generate_category(child) for child in parent_categories)
        }
        return dict(tree=OrderedDict(sorted(tree.items())))

    @classmethod
    def _create(cls, name, upper_id, shortname):

        upper = M.TroveCategory.query.get(trove_cat_id=upper_id)
        if upper_id == 0:
            path = name
            show_as_skill = True
        elif upper is None:
            raise TroveAdminException(('Invalid upper category.', "error"))
        else:
            path = upper.fullpath + " :: " + name
            show_as_skill = upper.show_as_skill

        newid = max(
            el.trove_cat_id for el in M.TroveCategory.query.find()) + 1
        shortname = h.slugify(shortname or name, True)[1]

        if upper:
            trove_type = upper.fullpath.split(' :: ')[0]
            fullpath_re = re.compile(fr'^{re.escape(trove_type)} :: ')  # e.g. scope within "Topic :: "
        else:
            # no parent, so making a top-level.  Don't limit fullpath_re, so enforcing global uniqueness
            fullpath_re = re.compile(r'')
        oldcat = M.TroveCategory.query.get(shortname=shortname, fullpath=fullpath_re)

        if oldcat:
            raise TroveAdminException(
                (f'A category with shortname "{shortname}" already exists ({oldcat.fullpath}).  Try a different, unique shortname', "error"),
                f'?categoryname={name}&shortname={shortname}',
                upper
            )
        else:
            M.TroveCategory(
                trove_cat_id=newid,
                trove_parent_id=upper_id,
                fullname=name,
                shortname=shortname,
                fullpath=path,
                show_as_skill=show_as_skill)
            return upper, ('Category "%s" successfully created.' % name,), ''

    @expose()
    @require_post()
    @validate(F.add_category_form, error_handler=index)
    def create(self, **kw):
        name = kw.get('categoryname')
        upper_id = int(kw.get('uppercategory_id', 0))
        shortname = kw.get('shortname', None)

        try:
            upper, flash_args, redir_params = self._create(name, upper_id, shortname)
        except TroveAdminException as ex:
            upper = ex.upper
            flash_args = ex.flash_args
            redir_params = ex.redir_params

        flash(*flash_args)

        if upper:
            redirect(f'/categories/{upper.trove_cat_id}/{redir_params}')
        else:
            redirect(f'/categories/{redir_params}')

    @expose()
    @require_post()
    @validate(F.remove_category_form, error_handler=index)
    def remove(self, **kw):
        cat = M.TroveCategory.query.get(trove_cat_id=int(kw['categoryid']))
        if cat.trove_parent_id:
            parent = M.TroveCategory.query.get(
                trove_cat_id=cat.trove_parent_id)
            redirecturl = '/categories/%s' % parent.trove_cat_id
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


class TroveCategorySiteAdminExtension(SiteAdminExtension):
    def update_sidebar_menu(self, links):
        enable_editing = config.get('trovecategories.enableediting', 'false')
        if enable_editing in ('admin', 'true'):
            links.append(SitemapEntry('Troves', '/categories',
                                      ui_icon=g.icons['admin']))
