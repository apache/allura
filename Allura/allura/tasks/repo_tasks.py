import shutil
import logging

from pylons import c

from allura.lib.decorators import task
from allura.lib.repository import RepositoryApp

@task
def init(**kwargs):
    from allura import model as M
    c.app.repo.init()
    M.Notification.post_user(
        c.user, c.app.repo, 'created',
        text='Repository %s/%s created' % (
            c.project.shortname, c.app.config.options.mount_point))

@task
def clone(cloned_from_path, cloned_from_name, cloned_from_url):
    from allura import model as M
    c.app.repo.init_as_clone(
        cloned_from_path,
        cloned_from_name,
        cloned_from_url)
    M.Notification.post_user(
        c.user, c.app.repo, 'created',
        text='Repository %s/%s created' % (
            c.project.shortname, c.app.config.options.mount_point))

@task
def reclone(*args, **kwargs):
    from allura import model as M
    from ming.orm import ThreadLocalORMSession
    repo = c.app.repo
    if repo is not None:
        shutil.rmtree(repo.full_fs_path, ignore_errors=True)
        repo.delete()
    ThreadLocalORMSession.flush_all()
    M.MergeRequest.query.remove(dict(
            app_config_id=c.app.config._id))
    clone(*args, **kwargs)

@task
def refresh(**kwargs):
    from allura import model as M
    log = logging.getLogger(__name__)
    #don't create multiple refresh tasks
    q = {
        'task_name': 'allura.tasks.repo_tasks.refresh',
        'state': {'$in': ['busy', 'ready']},
        'context.app_config_id': c.app.config._id,
        'context.project_id': c.project._id,
    }
    refresh_tasks_count = M.MonQTask.query.find(q).count()
    if refresh_tasks_count <= 1: #only this task
        c.app.repo.refresh()
        #checking if we have new commits arrived
        #during refresh and re-queue task if so
        new_commit_ids = c.app.repo.unknown_commit_ids()
        if len(new_commit_ids) > 0:
            refresh.post()
            log.info('New refresh task is queued due to new commit(s).')
    else:
        log.info('Refresh task for %s:%s skipped due to backlog', c.project.shortname, c.app.config.options.mount_point)

@task
def uninstall(**kwargs):
    from allura import model as M
    repo = c.app.repo
    if repo is not None:
        shutil.rmtree(repo.full_fs_path, ignore_errors=True)
        repo.delete()
    M.MergeRequest.query.remove(dict(
            app_config_id=c.app.config._id))
    super(RepositoryApp, c.app).uninstall(c.project)
    from ming.orm import ThreadLocalORMSession
    ThreadLocalORMSession.flush_all()

@task
def nop():
    log = logging.getLogger(__name__)
    log.info('nop')
