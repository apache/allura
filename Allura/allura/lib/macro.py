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
        if conf.tool_name.lower() == 'blog' and (mount_point is None or conf.options.mount_point==mount_point):
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
def projects(category=None, display_mode='grid', sort='last_updated',
        show_total=False, limit=100, labels='', award='', private=False):
    from allura.lib.widgets.project_list import ProjectList
    from allura.lib import utils
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
    if award:
        aw = M.Award.query.find(dict(
            created_by_neighborhood_id=c.project.neighborhood_id,
            short=award)).first()
        if aw:
            q['_id'] = {'$in': [grant.granted_to_project_id for grant in
                M.AwardGrant.query.find(dict(
                    granted_by_neighborhood_id=c.project.neighborhood_id,
                    award_id=aw._id))]}
    if category is not None:
        q['category_id'] = category._id
    sort_key, sort_dir = 'last_updated', pymongo.DESCENDING
    if sort == 'alpha':
        sort_key, sort_dir = 'name', pymongo.ASCENDING

    if private:
        # Only return private projects.
        # Can't filter these with a mongo query directly - have to iterate
        # through and check the ACL of each project.
        projects = []
        for chunk in utils.chunked_find(M.Project, q, sort_key=sort_key,
                sort_dir=sort_dir):
            projects.extend([p for p in chunk if p.private])
        total = len(projects)
        projects = projects[:int(limit)]
    else:
        total = None
        projects = M.Project.query.find(q).limit(int(limit)).sort(sort_key,
                sort_dir).all()

    pl = ProjectList()
    g.resource_manager.register(pl)
    response = pl.display(projects=projects, display_mode=display_mode)
    if show_total:
        if total is None:
            total = 0
            for p in M.Project.query.find(q):
                if h.has_access(p, 'read')():
                    total = total + 1
        response = '<p class="macro_projects_total">%s Projects</p>%s' % \
                (total, response)
    return response

@macro()
def project_screenshots():
    from allura.lib.widgets.project_list import ProjectScreenshots
    ps = ProjectScreenshots()
    g.resource_manager.register(ps)
    response = ps.display(project=c.project)
    return response

@macro()
def download_button():
    from allura import model as M
    from allura.lib.widgets.macros import DownloadButton
    button = DownloadButton(project=c.project)
    g.resource_manager.register(button)
    response = button.display(project=c.project)
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
