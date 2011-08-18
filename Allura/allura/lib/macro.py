import cgi
import shlex
import string
import logging

import pymongo
from pylons import c, g, request

from . import helpers as h
from . import security

log = logging.getLogger(__name__)

_macros = {}
class macro(object):

    def __init__(self, context=None):
        self._context = context

    def __call__(self, func):
        _macros[func.__name__] = (func, self._context)
        return func

class parse(object):

    def __init__(self, context):
        self._context = context

    def __call__(self, s):
        try:
            if s.startswith('quote '):
                return '[[' + s[len('quote '):] + ']]'
            try:
                parts = [ unicode(x, 'utf-8') for x in shlex.split(s.encode('utf-8')) ]
                if not parts: return '[[' + s + ']]'
                macro = self._lookup_macro(parts[0])
                if not macro: return  '[[' + s + ']]'
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

    def _lookup_macro(self, s):
        macro, context = _macros.get(s, None)
        if context is None or context == self._context:
            return macro
        else:
            return None

template_neighborhood_feeds = string.Template('''
<div class="neighborhood_feed_entry">
<h3><a href="$href">$title</a></h3>
<p>
by <em>$author</em>
<small>$ago</small>
</p>
<p>$description</p>
</div>
''')
@macro('neighborhood-wiki')
def neighborhood_feeds(tool_name, max_number=5, sort='pubdate'):
    from allura import model as M
    feed = M.Feed.query.find(
        dict(
            tool_name=tool_name,
            neighborhood_id=c.project.neighborhood._id))
    feed = feed.sort(sort, pymongo.DESCENDING).limit(int(max_number)).all()
    output = '\n'.join(
        template_neighborhood_feeds.substitute(dict(
                href=item.link,
                title=item.title,
                author=item.author_name,
                ago=h.ago(item.pubdate),
                description=item.description))
        for item in feed)
    return output

template_neighborhood_blog_posts = string.Template('''
<div class="neighborhood_feed_entry">
<h3><a href="$href">$title</a></h3>
<p>
by <em>$author</em>
<small>$ago</small>
</p>
$description
</div>
''')
@macro('neighborhood-wiki')
def neighborhood_blog_posts(max_number=5, sort='timestamp', summary=False):
    from forgeblog import model as BM
    posts = BM.BlogPost.query.find(dict(
        neighborhood_id=c.project.neighborhood._id,
        state='published'))
    posts = posts.sort(sort, pymongo.DESCENDING).limit(int(max_number)).all()
    output = '\n'.join(
        template_neighborhood_blog_posts.substitute(dict(
                href=post.url(),
                title=post.title,
                author=post.author().display_name,
                ago=h.ago(post.timestamp),
                description=summary and '&nbsp;' or g.markdown.convert(post.text)))
        for post in posts if security.has_access(post, 'read', project=post.app.project)() and
                             security.has_access(post.app.project, 'read', project=post.app.project)())
    return output

@macro()
def project_blog_posts(max_number=5, sort='timestamp', summary=False, mount_point=None):
    from forgeblog import model as BM
    app_config_ids = []
    for conf in c.project.app_configs:
        if conf.tool_name == 'blog' and (mount_point is None or conf.options.mount_point==mount_point):
            app_config_ids.append(conf._id)
    posts = BM.BlogPost.query.find({'state':'published','app_config_id':{'$in':app_config_ids}})
    posts = posts.sort(sort, pymongo.DESCENDING).limit(int(max_number)).all()
    output = '\n'.join(
        template_neighborhood_blog_posts.substitute(dict(
                href=post.url(),
                title=post.title,
                author=post.author().display_name,
                ago=h.ago(post.timestamp),
                description=summary and '&nbsp;' or g.markdown.convert(post.text)))
        for post in posts if security.has_access(post, 'read', project=post.app.project)() and
                             security.has_access(post.app.project, 'read', project=post.app.project)())
    return output

@macro('neighborhood-wiki')
def projects(
    category=None,
    display_mode='grid',
    sort='last_updated',
    show_total=False,
    limit=100,
    labels=''):
    from allura.lib.widgets.project_list import ProjectList
    from allura import model as M
    q = dict(
        neighborhood_id=c.project.neighborhood_id,
        deleted=False,
        shortname={'$ne':'--init--'})
    if labels:
        or_labels = labels.split('|')
        q['$or'] = [{'labels': {'$all': l.split(',')}} for l in or_labels]
    if category is not None:
        category = M.ProjectCategory.query.get(name=category)
    if category is not None:
        q['category_id'] = category._id
    pq = M.Project.query.find(q).limit(int(limit))
    if sort == 'alpha':
        pq.sort('name')
    else:
        pq.sort('last_updated', pymongo.DESCENDING)
    pl = ProjectList()
    g.resource_manager.register(pl)
    response = pl.display(projects=pq.all(), display_mode=display_mode)
    if show_total:
        total = 0
        for p in M.Project.query.find(q):
            if h.has_access(p, 'read')():
                total = total + 1
        response = '<p class="macro_projects_total">%s Projects</p>%s' % (total,response)
    return response

@macro()
def download_button(project=None, **kw):
    from allura import model as M
    from allura.lib.widgets.macros import DownloadButton
    if project is None:
        p = c.project
    else:
        p = M.Project.query.get(shortname=project)
    if not p:
        return '[[download_button %s (not found)]]' % project
    button = DownloadButton(project=p)
    g.resource_manager.register(button)
    response = button.display(project=p)
    return response

@macro()
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

@macro()
def img(src=None, **kw):
    attrs = ('%s="%s"' % t for t in kw.iteritems())
    included = request.environ.setdefault('allura.macro.att_embedded', set())
    included.add(src)
    if '://' in src:
        return '<img src="%s" %s/>' % (src, ' '.join(attrs))
    else:
        return '<img src="./attachment/%s" %s/>' % (src, ' '.join(attrs))


template_project_admins = string.Template('<a href="$url">$name</a><br/>')
@macro()
def project_admins():
    from allura import model as M
    output = ''
    admin_role = M.ProjectRole.query.get(project_id=c.project._id,name='Admin')
    if admin_role:
        output = '\n'.join(
            template_project_admins.substitute(dict(
                url=user_role.user.url(),
                name=user_role.user.display_name))
            for user_role in admin_role.users_with_role())
    return output
