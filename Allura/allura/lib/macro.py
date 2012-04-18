import cgi
import random
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

def get_projects_for_macro(category=None, display_mode='grid', sort='last_updated',
        show_total=False, limit=100, labels='', award='', private=False,
        columns=1, show_proj_icon=True, show_download_button=True, macro_type='projects'):
    from allura.lib.widgets.project_list import ProjectList
    from allura.lib import utils
    from allura import model as M
    # 'trove' is internal substitution for 'category' filter in wiki macro
    trove = category
    limit = int(limit)
    q = dict(
        neighborhood_id=c.project.neighborhood_id,
        deleted=False,
        shortname={'$ne':'--init--'})
    if labels:
        or_labels = labels.split('|')
        q['$or'] = [{'labels': {'$all': l.split(',')}} for l in or_labels]
    if trove is not None:
        trove = M.TroveCategory.query.get(fullpath=trove)
    if award:
        aw = M.Award.query.find(dict(
            created_by_neighborhood_id=c.project.neighborhood_id,
            short=award)).first()
        if aw:
            q['_id'] = {'$in': [grant.granted_to_project_id for grant in
                M.AwardGrant.query.find(dict(
                    granted_by_neighborhood_id=c.project.neighborhood_id,
                    award_id=aw._id))]}
    if trove is not None:
        q['trove_' + trove.type] = trove._id
    sort_key, sort_dir = 'last_updated', pymongo.DESCENDING
    if sort == 'alpha':
        sort_key, sort_dir = 'name', pymongo.ASCENDING
    elif sort == 'random':
        sort_key, sort_dir = None, None
    elif sort == 'last_registered':
        sort_key, sort_dir = '_id', pymongo.DESCENDING
    elif sort == '_id':
        sort_key, sort_dir = '_id', pymongo.DESCENDING

    if macro_type == 'projects':
        projects = []
        if private:
            # Only return private projects.
            # Can't filter these with a mongo query directly - have to iterate
            # through and check the ACL of each project.
            for chunk in utils.chunked_find(M.Project, q, sort_key=sort_key,
                    sort_dir=sort_dir):
                projects.extend([p for p in chunk if p.private])
            total = len(projects)
            if sort == 'random':
                projects = random.sample(projects, min(limit, total))
            else:
                projects = projects[:limit]
        else:
            total = None
            if sort == 'random':
                # MongoDB doesn't have a random sort built in, so...
                # 1. Do a direct pymongo query (faster than ORM) to fetch just the
                #    _ids of objects that match our criteria
                # 2. Choose a random sample of those _ids
                # 3. Do an ORM query to fetch the objects with those _ids
                # 4. Shuffle the results
                from ming.orm import mapper
                m = mapper(M.Project)
                collection = M.main_doc_session.db[m.collection.m.collection_name]
                docs = list(collection.find(q, {'_id': 1}))
                if docs:
                    ids = [doc['_id'] for doc in
                            random.sample(docs, min(limit, len(docs)))]
                    if '_id' in q:
                        ids = list(set(q['_id']['$in']).intersection(ids))
                    q['_id'] = {'$in': ids}
                    projects = M.Project.query.find(q).all()
                    random.shuffle(projects)
            else:
                projects = M.Project.query.find(q).limit(limit).sort(sort_key,
                    sort_dir).all()

    elif macro_type == 'my_projects':
        projects = []
        myproj_user = c.user.anonymous()

        if c.project.neighborhood.name == "Users" and c.project.name[:2] == u"u/":
            username = c.project.name[2:]
            myproj_user = M.User.query.get(username=username)
            if 'neighborhood_id' in q:
                del q['neighborhood_id']
        else:
            admin_role_id = M.ProjectRole.query.get(project_id=c.project._id,name='Admin')._id
            if c.user is None or c.user == c.user.anonymous():
                project_users_roles = M.ProjectRole.query.find(dict(name=None, project_id=c.project._id)).all()
                for ur in project_users_roles:
                    if admin_role_id in ur.roles:
                        myproj_user = ur.user
                        break
            else:
                myproj_user = c.user

        # Get projects ids
        ids = []
        for p in myproj_user.my_projects():
            ids.append(p._id)
        if '_id' in q:
            ids = list(set(q['_id']['$in']).intersection(ids))
        q['_id'] = {'$in': ids}

        if sort == 'random':
            ids = random.sample(ids, min(limit, len(ids)))
            projects = M.Project.query.find(q).all()
            random.shuffle(projects)
        else:
            projects = M.Project.query.find(q).limit(limit).sort(sort_key,
                sort_dir).all()

    pl = ProjectList()
    g.resource_manager.register(pl)
    response = pl.display(projects=projects, display_mode=display_mode,
                          columns=columns, show_proj_icon=show_proj_icon,
                          show_download_button=show_download_button)
    if show_total:
        if total is None:
            total = 0
            for p in M.Project.query.find(q):
                if h.has_access(p, 'read')():
                    total = total + 1
        response = '<p class="macro_projects_total">%s Projects</p>%s' % \
                (total, response)
    return response


@macro('neighborhood-wiki')
def projects(category=None, display_mode='grid', sort='last_updated',
        show_total=False, limit=100, labels='', award='', private=False,
        columns=1, show_proj_icon=True, show_download_button=True):
    return get_projects_for_macro(category=category, display_mode=display_mode, sort=sort, 
                   show_total=show_total, limit=limit, labels=labels, award=award, private=private,
                   columns=columns, show_proj_icon=show_proj_icon, show_download_button=show_download_button,
                   macro_type='projects')

@macro()
def my_projects(category=None, display_mode='grid', sort='last_updated',
        show_total=False, limit=100, labels='', award='', private=False,
        columns=1, show_proj_icon=True, show_download_button=True):
    return get_projects_for_macro(category=category, display_mode=display_mode, sort=sort, 
                   show_total=show_total, limit=limit, labels=labels, award=award, private=private,
                   columns=columns, show_proj_icon=show_proj_icon, show_download_button=show_download_button,
                   macro_type='my_projects')

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
