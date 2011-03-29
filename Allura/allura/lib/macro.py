import cgi
import shlex
import logging

import pymongo
from tg import c, g, request

from . import helpers as h

log = logging.getLogger(__name__)

_macros = {}

def macro(func):
    _macros[func.__name__] = func
    return func

def parse(s):
    try:
        if s.startswith('quote '):
            return '[[' + s[len('quote '):] + ']]'
        try:
            parts = [ unicode(x, 'utf-8') for x in shlex.split(s.encode('utf-8')) ]
            if not parts: return None
            macro = _macros.get(parts[0], None)
            if not macro: return None
            for t in parts[1:]:
                if '=' not in t:
                    return '[-%s: missing =-]' % ' '.join(parts)
            args = dict(t.split('=', 1) for t in parts[1:])
            response = macro(**h.encode_keys(args))
            return response
        except (ValueError, TypeError), ex:
            msg = cgi.escape(u'[[%s]] (%s)' % (s, repr(ex)))
            return '\n<div class="error"><pre><code>%s</code></pre></div>' % msg
    except Exception, ex:
        raise
        return '[[Error parsing %s: %s]]' % (s, ex)

@macro
def projects(category=None, display_mode='grid', sort='last_updated'):
    from allura.lib.widgets.project_list import ProjectList
    from allura import model as M
    q = dict(
        neighborhood_id=c.project.neighborhood_id,
        deleted=False,
        shortname={'$ne':'--init--'})
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
    g.resource_manager.register(pl)
    response = pl.display(projects=pq.all(), display_mode=display_mode)
    return response

@macro
def include(ref=None, **kw):
    from allura import model as M
    from allura.lib.widgets.macros import Include
    if ref is None:
        return '[-include-]'
    link = M.Shortlink.lookup(ref)
    if not link:
        return '[[include %s (not found)]]' % ref
    artifact = link.ref.artifact
    if artifact is None:
        return '[[include (artifact not found)]]' % ref
    included = request.environ.setdefault('allura.macro.included', set())
    if artifact in included:
        return '[[include %s (already included)]' % ref
    else:
        included.add(artifact)
    sb = Include()
    g.resource_manager.register(sb)
    response = sb.display(artifact=artifact, attrs=kw)
    return response

@macro
def img(src=None, **kw):
    attrs = ('%s="%s"' % t for t in kw.iteritems())
    included = request.environ.setdefault('allura.macro.att_embedded', set())
    included.add(src)
    if '://' in src:
        return '<img src="%s" %s/>' % (src, ' '.join(attrs))
    else:
        return '<img src="./attachment/%s" %s/>' % (src, ' '.join(attrs))
