from functools import wraps

from ming.orm import ThreadLocalORMSession

from allura.model.project import Project, Neighborhood, AppConfig
from allura.model.auth import User
from allura.model.discuss import Discussion, Thread, Post


def flush_on_return(fn):
    @wraps(fn)
    def new_fn(*args, **kwargs):
        result = fn(*args, **kwargs)
        ThreadLocalORMSession.flush_all()
        return result
    return new_fn


@flush_on_return
def create_project(shortname):
    neighborhood = create_neighborhood()
    return Project(shortname=shortname,
                   database_uri='mim://test/myproject_db',
                   neighborhood_id=neighborhood._id,
                   is_root=True)


@flush_on_return
def create_neighborhood():
    neighborhood = Neighborhood(url_prefix='http://example.com/myproject')
    return neighborhood


@flush_on_return
def create_app_config(project, mount_point):
    return AppConfig(
        project_id=project._id,
        tool_name='myapp',
        options={'mount_point': 'my_mounted_app'},
        acl={})


@flush_on_return
def create_post(slug):
    discussion = create_discussion()
    thread = create_thread(discussion=discussion)
    author = create_user()
    return Post(slug=slug,
                thread_id=thread._id,
                discussion_id=discussion._id,
                author_id=author._id)


@flush_on_return
def create_thread(discussion):
    return Thread(discussion_id=discussion._id)


@flush_on_return
def create_discussion():
    return Discussion()


@flush_on_return
def create_user():
    return User()

