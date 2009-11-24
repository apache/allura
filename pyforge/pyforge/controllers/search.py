from tg import expose, redirect, flash, config, validate
from tg.decorators import with_trailing_slash
from formencode import validators as V

from pyforge.lib import search

class SearchController(object):

    @expose('pyforge.templates.search_index')
    @validate(dict(q=V.UnicodeString(),
                   history=V.StringBool(if_empty=False)))
    @with_trailing_slash
    def index(self, q=None, history=None):
        results = []
        count=0
        if q is None:
            q = ''
        else:
            search_query = '%s AND is_history_b:%s' % (q, history)
            results = search.search(search_query, is_history_b=history)
            if results: count=results.hits
        return dict(q=q, history=history, results=results or [], count=count)

