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

from tg import expose, validate, request
from tg.decorators import with_trailing_slash, without_trailing_slash
from formencode import validators as V
from tg import tmpl_context as c
from webob import exc
import pymongo

from allura.lib.search import search_app
from allura.lib.widgets.search import SearchResults
from allura.app import SitemapEntry
from allura import model as M
from allura.lib.widgets import project_list as plw
from allura.controllers import BaseController


class W:
    project_summary = plw.ProjectSummary()
    search_results = SearchResults()


class SearchController(BaseController):

    @expose('jinja:allura:templates/search_index.html')
    @validate(dict(q=V.UnicodeString(),
                   history=V.StringBool(if_empty=False)))
    @with_trailing_slash
    def index(self, q=None, history=False, **kw):
        c.search_results = W.search_results
        search_params = kw
        search_params.update({
            'q': q,
            'history': history,
            'app': False,
        })
        d = search_app(**search_params)
        d['search_comments_disable'] = True
        d['hide_app_project_switcher'] = True
        return d


class ProjectBrowseController(BaseController):

    def __init__(self, category_name=None, parent_category=None):
        self.parent_category = parent_category
        self.nav_stub = '/browse/'
        self.additional_filters = {}
        if category_name:
            parent_id = parent_category and parent_category._id or None
            self.category = M.ProjectCategory.query.find(
                dict(name=category_name, parent_id=parent_id)).first()
            if not self.category:
                raise exc.HTTPNotFound(request.path)
        else:
            self.category = None

    def _build_title(self):
        title = "All Projects"
        if self.category:
            title = self.category.label
            if self.parent_category:
                title = f"{self.parent_category.label}: {title}"
        return title

    def _build_nav(self):
        categories = M.ProjectCategory.query.find(
            {'parent_id': None}).sort('name').all()
        nav = []
        for cat in categories:
            nav.append(SitemapEntry(
                cat.label,
                self.nav_stub + cat.name,
            ))
            if (self.category and self.category._id == cat._id and cat.subcategories) or (
                    self.parent_category and self.parent_category._id == cat._id):
                for subcat in cat.subcategories:
                    nav.append(SitemapEntry(
                        subcat.label,
                        self.nav_stub + cat.name + '/' + subcat.name,
                    ))
        return nav

    def _find_projects(self, sort='alpha', limit=None, start=0):
        if self.category:
            ids = [self.category._id]
            # warning! this is written with the assumption that categories
            # are only two levels deep like the existing site
            if self.category.subcategories:
                ids = ids + [cat._id for cat in self.category.subcategories]
            pq = M.Project.query.find(
                dict(category_id={'$in': ids}, deleted=False, **self.additional_filters))
        else:
            pq = M.Project.query.find(
                dict(deleted=False, **self.additional_filters))
        if sort == 'alpha':
            pq.sort('name')
        else:
            pq.sort('last_updated', pymongo.DESCENDING)
        count = pq.count()
        if limit:
            projects = pq.skip(start).limit(int(limit)).all()
        else:
            projects = pq.all()
        return (projects, count)

    @expose()
    def _lookup(self, category_name, *remainder):
        return ProjectBrowseController(category_name=category_name, parent_category=self.category), remainder

    @expose('jinja:allura:templates/project_list.html')
    @without_trailing_slash
    def index(self, **kw):
        c.project_summary = W.project_summary
        projects, count = self._find_projects()
        title = self._build_title()
        c.custom_sidebar_menu = self._build_nav()
        return dict(projects=projects, title=title, text=None)
