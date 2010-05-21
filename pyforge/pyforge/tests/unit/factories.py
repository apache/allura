from ming.orm import ThreadLocalORMSession

from pyforge.model.project import Project, Neighborhood, AppConfig


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
    return app_config

