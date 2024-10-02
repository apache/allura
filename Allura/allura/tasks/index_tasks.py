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
from __future__ import annotations

import sys
import logging
from collections.abc import Iterable
from contextlib import contextmanager
import typing

from tg import app_globals as g
from tg import tmpl_context as c
from webob.exc import HTTPRequestEntityTooLarge

from allura.lib import helpers as h
from allura.lib.decorators import task
from allura.lib.exceptions import CompoundError
from allura.lib.solr import make_solr_from_config
import six

if typing.TYPE_CHECKING:
    import pysolr


log = logging.getLogger(__name__)


def __get_solr(solr_hosts=None, solr_creds=()):
    return make_solr_from_config(solr_hosts, push_servers_auths=solr_creds) if solr_hosts else g.solr


def __add_objects(objects, solr_hosts=None, solr_creds=()):
    solr_instance = __get_solr(solr_hosts, solr_creds)
    solr_instance.add([obj.solarize() for obj in objects])


def __del_objects(object_solr_ids):
    solr_instance = __get_solr()
    solr_query = 'id:({})'.format(' || '.join(object_solr_ids))
    solr_instance.delete(q=solr_query)


def check_for_dirty_ming_records(msg_prefix, ming_sessions=None):
    """
    A debugging helper to diagnose issues with code that unintentionally modifies records, causing them to be written
    back to mongo (potentially clobbering values written by a parallel task/request)
    """
    if ming_sessions is None:
        from allura.model import main_orm_session, artifact_orm_session, project_orm_session
        ming_sessions = [main_orm_session, artifact_orm_session, project_orm_session]
    for sess in ming_sessions:
        dirty_objects = list(sess.uow.dirty)
        if dirty_objects:
            log.warning(msg_prefix + ' changed objects, causing writes back to mongo: %s',
                        dirty_objects)


@task
def add_projects(project_ids):
    from allura.model.project import Project
    projects = Project.query.find(dict(_id={'$in': project_ids})).all()
    __add_objects(projects)
    check_for_dirty_ming_records('add_projects task')


@task
def del_projects(project_solr_ids):
    __del_objects(project_solr_ids)


@task
def add_users(user_ids):
    from allura.model import User
    users = User.query.find(dict(_id={'$in': user_ids})).all()
    __add_objects(users)


@task
def del_users(user_solr_ids):
    __del_objects(user_solr_ids)


@task
def add_artifacts(ref_ids, update_solr=True, update_refs=True,
                  solr_hosts: Iterable[str] = (),
                  solr_creds: Iterable[tuple[str, str]] = (),
                  ):
    '''
    Add the referenced artifacts to SOLR and shortlinks.
    '''
    from allura import model as M
    from allura.lib.search import find_shortlinks

    # task params end up as instrumented lists, need to make this a list of plain tuples
    solr_creds = [tuple(cred) for cred in solr_creds]

    exceptions = []
    solr_updates = []
    with _indexing_disabled(M.session.artifact_orm_session._get()):
        for ref in M.ArtifactReference.query.find(dict(_id={'$in': ref_ids})):
            try:
                artifact = ref.artifact
                if artifact is None:
                    continue
                # c.project and .app are normally set, so keep using them
                # During a reindex or other batch jobs, they are not though, so set it from artifact
                app = getattr(c, 'app', None) or artifact.app
                project = getattr(c, 'project', None) or artifact.project
                with h.push_config(c, project=project, app=app):
                    s = artifact.solarize()
                    if s is None:
                        continue
                    if update_solr:
                        solr_updates.append(s)
                    if update_refs:
                        if isinstance(artifact, M.Snapshot):
                            continue
                        # Find shortlinks in the raw text, not the escaped html
                        # created by the `solarize()`.
                        link_text = artifact.index().get('text') or ''
                        shortlinks = find_shortlinks(link_text)
                        ref.references = [link.ref_id for link in shortlinks]
            except Exception:
                log.error('Error indexing artifact %s', ref._id)
                exceptions.append(sys.exc_info())

        def _add_artifact(solr: pysolr.Solr, artifacts: list):
            try:
                solr.add(artifacts)
            except HTTPRequestEntityTooLarge:
                if len(artifacts) > 1:
                    log.warning(f"Solr.add raised HTTPRequestEntityTooLarge. Splitting {len(artifacts)} updates into two batches.")
                    _add_artifact(solr, artifacts[:len(artifacts) // 2])
                    _add_artifact(solr, artifacts[len(artifacts) // 2:])
                else:
                    log.info("Solr.add raised HTTPRequestEntityTooLarge but there is only one artifact. Raising exception.")
                    raise

        _add_artifact(__get_solr(solr_hosts, solr_creds), solr_updates)

    if len(exceptions) == 1:
        raise exceptions[0][1].with_traceback(exceptions[0][2])
    if exceptions:
        raise CompoundError(*exceptions)
    check_for_dirty_ming_records('add_artifacts task')


@task
def del_artifacts(ref_ids):
    from allura import model as M
    if ref_ids:
        __del_objects(ref_ids)
        M.ArtifactReference.query.remove(dict(_id={'$in': ref_ids}))
        M.Shortlink.query.remove(dict(ref_id={'$in': ref_ids}))


@task
def solr_del_project_artifacts(project_id):
    g.solr.delete(q='project_id_s:%s' % project_id)


@task
def commit():
    g.solr.commit()


@task
def solr_del_tool(project_id, mount_point_s):
    g.solr.delete(q=f'project_id_s:"{project_id}" AND mount_point_s:"{mount_point_s}"')


@contextmanager
def _indexing_disabled(session):
    session.disable_index = session.skip_mod_date = True
    try:
        yield session
    finally:
        session.disable_index = session.skip_mod_date = False
