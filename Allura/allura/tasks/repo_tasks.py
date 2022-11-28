#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

import shutil
import logging
import traceback

from tg import tmpl_context as c, app_globals as g
from ming.odm import session

from allura.lib.decorators import task
from allura.lib.repository import RepositoryApp
from allura.lib.utils import skip_mod_date


@task
def init(**kwargs):
    c.app.repo.init()


@task
def clone(cloned_from_path, cloned_from_name, cloned_from_url):
    from allura import model as M
    try:
        c.app.repo.init_as_clone(
            cloned_from_path,
            cloned_from_name,
            cloned_from_url)
        M.Notification.post_user(
            c.user, c.app.repo, 'created',
            text='Repository {}/{} created'.format(
                c.project.shortname, c.app.config.options.mount_point))
        M.AuditLog.log('{}: import completed from "{}"'.format(
            c.app.config.options['mount_point'], cloned_from_url))
    except Exception:
        g.post_event('repo_clone_task_failed', cloned_from_url,
                     cloned_from_path, traceback.format_exc())


@task
def reclone(*args, **kwargs):
    from allura import model as M
    from ming.orm import ThreadLocalORMSession
    repo = c.app.repo
    if repo is not None:
        shutil.rmtree(repo.full_fs_path, ignore_errors=True)
    M.MergeRequest.query.remove(dict(
        app_config_id=c.app.config._id))
    ThreadLocalORMSession.flush_all()
    clone(*args, **kwargs)


@task
def refresh(**kwargs):
    from allura import model as M
    log = logging.getLogger(__name__)
    # don't create multiple refresh tasks
    q = {
        'task_name': 'allura.tasks.repo_tasks.refresh',
        'state': {'$in': ['busy', 'ready']},
        'context.app_config_id': c.app.config._id,
        'context.project_id': c.project._id,
    }
    refresh_tasks_count = M.MonQTask.query.find(q).count()
    if refresh_tasks_count <= 1:  # only this task
        c.app.repo.refresh()
        # checking if we have new commits arrived
        # during refresh and re-queue task if so
        new_commit_ids = c.app.repo.unknown_commit_ids()
        if len(new_commit_ids) > 0:
            refresh.post()
            log.info('New refresh task is queued due to new commit(s).')
    else:
        log.info('Refresh task for %s:%s skipped due to backlog',
                 c.project.shortname, c.app.config.options.mount_point)


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


@task
def reclone_repo(*args, **kwargs):
    from allura import model as M
    try:
        nbhd = M.Neighborhood.query.get(url_prefix='/%s/' % kwargs['prefix'])
        c.project = M.Project.query.get(
            shortname=kwargs['shortname'], neighborhood_id=nbhd._id)
        c.app = c.project.app_instance(kwargs['mount_point'])
        source_url = c.app.config.options.get('init_from_url')
        source_path = c.app.config.options.get('init_from_path')
        c.app.repo.init_as_clone(source_path, None, source_url)
        M.Notification.post_user(
            c.user, c.app.repo, 'created',
            text='Repository {}/{} created'.format(
                c.project.shortname, c.app.config.options.mount_point))
    except Exception:
        g.post_event('repo_clone_task_failed', source_url,
                     source_path, traceback.format_exc())


@task
def tarball(revision, path):
    log = logging.getLogger(__name__)
    if revision:
        repo = c.app.repo
        status = repo.get_tarball_status(revision, path)
        if status == 'complete':
            log.info(
                'Skipping snapshot for repository: %s:%s rev %s because it is already %s' %
                (c.project.shortname, c.app.config.options.mount_point, revision, status))
        else:
            try:
                repo.tarball(revision, path)
            except Exception:
                log.error(
                    'Could not create snapshot for repository: %s:%s revision %s path %s' %
                    (c.project.shortname, c.app.config.options.mount_point, revision, path), exc_info=True)
                raise
    else:
        log.warn(
            'Skipped creation of snapshot: %s:%s because revision is not specified' %
            (c.project.shortname, c.app.config.options.mount_point))


@task
def merge(merge_request_id):
    from allura import model as M
    mr = M.MergeRequest.query.get(_id=merge_request_id)
    mr.app.repo.merge(mr)
    mr.add_meta_post(changes={'Status': [mr.status, 'merged']})
    mr.status = 'merged'
    g.director.create_activity(c.user, 'merged', mr, target=mr.app,
                               related_nodes=[c.project], tags=['merge-request'])
    session(mr).flush(mr)


@task
def can_merge(merge_request_id):
    from allura import model as M
    mr = M.MergeRequest.query.get(_id=merge_request_id)
    result = mr.app.repo.can_merge(mr)
    mr.set_can_merge_cache(result)


@task
def determine_mr_commits(merge_request_id):
    from allura import model as M
    mr = M.MergeRequest.query.get(_id=merge_request_id)
    mr.commits  # build & cache the commits
