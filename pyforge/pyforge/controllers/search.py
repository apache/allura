from tg import expose, redirect, flash, config, validate, request
from tg.decorators import with_trailing_slash, without_trailing_slash
from formencode import validators as V
from pylons import c
from webob import exc
import pymongo

from pyforge.lib import search
from pyforge.app import SitemapEntry
from pyforge import model as M
from pyforge.lib.widgets import project_list as plw

class W:
    project_summary = plw.ProjectSummary()

class SearchController(object):

    @expose('pyforge.templates.search_index')
    @validate(dict(q=V.UnicodeString(),
                   history=V.StringBool(if_empty=False)))
    @with_trailing_slash
    def index(self, q=None, history=False, **kw):
        results = []
        count=0
        if not q:
            q = ''
        else:
            results = search.search(
                q, 
                fq='is_history_b:%s' % history)
            if results: count=results.hits
        return dict(q=q, history=history, results=results or [], count=count)


class ProjectBrowseController(object):
    def __init__(self, category_name=None, parent_category=None):
        self.parent_category = parent_category
        self.nav_stub = '/browse/'
        self.additional_filters = {}
        if category_name:
            parent_id = parent_category and parent_category._id or None
            self.category = M.ProjectCategory.query.find(dict(name=category_name,parent_id=parent_id)).first()
            if not self.category:
                raise exc.HTTPNotFound, request.path
        else:
            self.category = None
    
    def _build_title(self):
        title = "All Projects"
        if self.category:
            title = self.category.label
            if self.parent_category:
                title = "%s: %s" % (self.parent_category.label, title)
        return title

    def _build_nav(self):
        categories = M.ProjectCategory.query.find({'parent_id':None}).sort('name').all()
        nav = []
        for cat in categories:
            nav.append(SitemapEntry(
                cat.label, 
                self.nav_stub+cat.name, 
                className='nav_child'))
            if (self.category and self.category._id == cat._id and cat.subcategories) or (
                self.parent_category and self.parent_category._id == cat._id):
                for subcat in cat.subcategories:
                    nav.append(SitemapEntry(
                        subcat.label, 
                        self.nav_stub+cat.name+'/'+subcat.name, 
                        className='nav_child2'))
        return nav

    def _find_projects(self,sort='alpha'):
        if self.category:
            ids = [self.category._id]
            # warning! this is written with the assumption that categories
            # are only two levels deep like the existing site
            if self.category.subcategories:
                ids = ids + [cat._id for cat in self.category.subcategories]
            pq = M.Project.query.find(dict(category_id={'$in':ids}, deleted=False, **self.additional_filters))
        else:
            pq = M.Project.query.find(dict(deleted=False, **self.additional_filters))
        if sort=='alpha':
            pq.sort('name')
        else:
            pq.sort('last_updated', pymongo.DESCENDING)
        projects = pq.all()
        return projects

    @expose()
    def _lookup(self, category_name, *remainder):
        return ProjectBrowseController(category_name=category_name, parent_category=self.category), remainder

    @expose('pyforge.templates.project_list')
    @without_trailing_slash
    def index(self, **kw):
        c.project_summary = W.project_summary
        projects = self._find_projects()
        title=self._build_title()
        c.custom_sidebar_menu = self._build_nav()
        return dict(projects=projects,title=title,text=None)
