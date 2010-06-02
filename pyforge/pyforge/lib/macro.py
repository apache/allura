import shlex
import logging

import ew
import pymongo
from pylons import c

from . import helpers as h

log = logging.getLogger(__name__)

_macros = {}

def macro(func):
    _macros[func.__name__] = func
    return func

def parse(s):
    parts = [ unicode(x, 'utf-8') for x in shlex.split(s.encode('utf-8')) ]
    if not parts: return None
    macro = _macros.get(parts[0], None)
    if not macro: return None
    try:
        args = dict(t.split('=', 1) for t in parts[1:])
        response = macro(**h.encode_keys(args))
        return response
    except (ValueError, TypeError), ex:
        raise
        print ex
        import pdb; pdb.set_trace()
        log.exception('Error in macro call on %s', s)
        return None

@macro
def projects(category=None, display_mode='grid', sort='last_updated'):
    from pyforge.lib.widgets.project_list import ProjectList
    from pyforge import model as M
    q = dict(
        neighborhood_id=c.project.neighborhood_id,
        deleted=False,
        shortname={'$ne':'__init__'})
    if category is not None:
        category = M.ProjectCategory.query.get(name=category)
    if category is not None:
        q['category_id'] = category._id
    pq = M.Project.query.find(q)
    if sort == 'alpha':
        pq.sort('name')
    else:
        pq.sort('last_updated', pymongo.DESCENDING)
    pl = ProjectList()
    ew.ResourceManager.get().register(pl)
    response = pl.display(projects=pq.all(), display_mode=display_mode)
    return response
