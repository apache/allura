from functools import wraps

from allura import model as M

from ming.orm.ormsession import ThreadLocalORMSession

from pylons import c

def with_user_project(username):
    def _with_user_project(func):
        @wraps(func)
        def wrapped(*args, **kw):
            user = M.User.by_username(username)
            c.user = user
            n = M.Neighborhood.query.get(name='Users')
            shortname = 'u/' + username
            p = M.Project.query.get(shortname=shortname, neighborhood_id=n._id)
            if not p:
                n.register_project(shortname, user=user, user_project=True)
                ThreadLocalORMSession.flush_all()
                ThreadLocalORMSession.close_all()
            return func(*args, **kw)
        return wrapped
    return _with_user_project

def with_tool(project_shortname, ep_name, mount_point=None, mount_label=None,
        ordinal=None, post_install_hook=None, username='test-admin',
        **override_options):
    def _with_tool(func):
        @wraps(func)
        def wrapped(*args, **kw):
            c.user = M.User.by_username(username)
            p = M.Project.query.get(shortname=project_shortname)
            c.project = p
            if mount_point and not p.app_instance(mount_point):
                c.app = p.install_app(ep_name, mount_point, mount_label, ordinal, **override_options)
                if post_install_hook:
                    post_install_hook(c.app)
                while M.MonQTask.run_ready('setup'):
                    pass
                ThreadLocalORMSession.flush_all()
                ThreadLocalORMSession.close_all()
            elif mount_point:
                c.app = p.app_instance(mount_point)
            return func(*args, **kw)
        return wrapped
    return _with_tool

with_discussion = with_tool('test', 'Discussion', 'discussion')
with_link = with_tool('test', 'Link', 'link')
with_tracker = with_tool('test', 'Tickets', 'bugs')
with_wiki = with_tool('test', 'Wiki', 'wiki')
with_git = with_tool('test', 'Git', 'src-git', 'Git', type='git')
with_hg = with_tool('test', 'Hg', 'src-hg', 'Mercurial', type='hg')
with_svn = with_tool('test', 'SVN', 'src', 'SVN')

def with_repos(func):
    @wraps(func)
    @with_git
    @with_hg
    @with_svn
    def wrapped(*args, **kw):
        return func(*args, **kw)
    return wrapped
