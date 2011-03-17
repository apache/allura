import shutil

from pylons import c

from allura import model as M
from allura.lib.utils import task, event_listeners
from allura.lib.repository import RepositoryApp

@task
def event(data):
    for e in event_listeners(data['event_type']):
        e()

@task
def repo_init(data):
    c.app.repo.init()
    M.Notification.post_user(
        c.user, c.app.repo, 'created',
        text='Repository %s/%s created' % (
            c.project.shortname, c.app.config.options.mount_point))

@task
def repo_clone(data):
    c.app.repo.init_as_clone(
        data['cloned_from_path'],
        data['cloned_from_name'],
        data['cloned_from_url'])
    M.Notification.post_user(
        c.user, c.app.repo, 'created',
        text='Repository %s/%s created' % (
            c.project.shortname, c.app.config.options.mount_point))

@task
def repo_refresh(data):
    c.app.repo.refresh()

@task
def repo_uninstall(data):
    repo = c.app.repo
    if repo is not None:
        shutil.rmtree(repo.full_fs_path, ignore_errors=True)
        repo.delete()
    M.MergeRequest.query.remove(dict(
            app_config_id=c.app.config._id))
    super(RepositoryApp, c.app).uninstall(c.project)
