from ming.orm import ThreadLocalORMSession

from pyforge.model.project import Project, Neighborhood, AppConfig
from pyforge.model.auth import User
from pyforge.model.discuss import Discussion, Thread, Post


def create_project(shortname):
    neighborhood = create_neighborhood()
    project = Project(shortname=shortname,
                      database='myproject_db',
                      neighborhood_id=neighborhood._id)
    ThreadLocalORMSession.flush_all()
    return project


def create_neighborhood():
    neighborhood = Neighborhood(url_prefix='http://example.com/myproject')
    ThreadLocalORMSession.flush_all()
    return neighborhood


def create_app_config(project, mount_point):
    app_config = AppConfig(
        project_id=project._id,
        tool_name='myapp',
        options={'mount_point': 'my_mounted_app'},
        acl={})
    ThreadLocalORMSession.flush_all()
    return AppConfig.query.get(_id=app_config._id)


def create_post(slug):
    discussion = create_discussion()
    thread = create_thread(discussion=discussion)
    author = create_user()
    return Post(slug=slug,
                thread_id=thread._id,
                discussion_id=discussion._id,
                author_id=author._id)
    ThreadLocalORMSession.flush_all()
    return post


def create_thread(discussion):
    thread = Thread(discussion_id=discussion._id)
    ThreadLocalORMSession.flush_all()
    return thread


def create_discussion():
    discussion = Discussion()
    ThreadLocalORMSession.flush_all()
    return discussion


def create_user():
    user = User()
    ThreadLocalORMSession.flush_all()
    return user

