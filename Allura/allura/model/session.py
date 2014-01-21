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

import logging
import pymongo

from ming import Session
from ming.orm.base import state
from ming.orm.ormsession import ThreadLocalORMSession, SessionExtension
from contextlib import contextmanager

from allura.lib.utils import chunked_list
from allura.tasks import index_tasks

log = logging.getLogger(__name__)


class ArtifactSessionExtension(SessionExtension):

    def __init__(self, session):
        SessionExtension.__init__(self, session)
        self.objects_added = []
        self.objects_modified = []
        self.objects_deleted = []

    def before_flush(self, obj=None):
        if obj is None:
            self.objects_added = list(self.session.uow.new)
            self.objects_modified = list(self.session.uow.dirty)
            self.objects_deleted = list(self.session.uow.deleted)
        else:  # pragma no cover
            st = state(obj)
            if st.status == st.new:
                self.objects_added = [obj]
            elif st.status == st.dirty:
                self.objects_modified = [obj]
            elif st.status == st.deleted:
                self.objects_deleted = [obj]

    def after_flush(self, obj=None):
        "Update artifact references, and add/update this artifact to solr"
        if not getattr(self.session, 'disable_artifact_index', False):
            from pylons import app_globals as g
            from .index import ArtifactReference, Shortlink
            from .session import main_orm_session
            # Ensure artifact references & shortlinks exist for new objects
            arefs = []
            try:
                arefs = [
                    ArtifactReference.from_artifact(o)
                    for o in self.objects_added + self.objects_modified]
                for obj in self.objects_added + self.objects_modified:
                    Shortlink.from_artifact(obj)
                # Flush shortlinks
                main_orm_session.flush()
            except Exception:
                log.exception(
                    "Failed to update artifact references. Is this a borked project migration?")
            self.update_index(self.objects_deleted, arefs)
            for obj in self.objects_added:
                g.zarkov_event('create', extra=obj.index_id())
            for obj in self.objects_modified:
                g.zarkov_event('modify', extra=obj.index_id())
            for obj in self.objects_deleted:
                g.zarkov_event('delete', extra=obj.index_id())
        self.objects_added = []
        self.objects_modified = []
        self.objects_deleted = []

    def update_index(self, objects_deleted, arefs):
        # Post delete and add indexing operations
        if objects_deleted:
            index_tasks.del_artifacts.post(
                [obj.index_id() for obj in objects_deleted])
        add_task = None
        if arefs:
            add_task = index_tasks.add_artifacts.post([aref._id for aref in arefs])
        try:
            l = logging.getLogger('allura.debug7047')
            from tg import request
            task = request.environ.get('task')
            if task and task.task_name == 'forgetracker.tasks.bulk_edit':
                l.debug('session: %s %s', self.session.impl.db, self.session)
                l.debug('arefs: %s', arefs)
                l.debug('objects_added: %s', [o._id for o in self.objects_added])
                l.debug('objects_modified: %s', [o._id for o in self.objects_modified])
                l.debug('objects_deleted: %s', [o._id for o in self.objects_deleted])
                l.debug('add_artifacts task: %s', add_task)
        except:
            pass


class BatchIndexer(ArtifactSessionExtension):

    """
    Tracks needed search index operations over the life of a
    :class:`ming.odm.session.ThreadLocalODMSession` session, and performs them
    in a batch when :meth:`flush` is called.
    """
    to_delete = set()
    to_add = set()

    def __init__(self, session):
        ArtifactSessionExtension.__init__(self, session)

    def update_index(self, objects_deleted, arefs_added):
        """
        Caches adds and deletes for handling later.  Called after each flush of
        the parent session.

        :param objects_deleted: :class:`allura.model.artifact.Artifact`
          instances that were deleted in the flush.

        :param arefs_added: :class:`allura.model.artifact.ArtifactReference`
          instances for all ``Artifact`` instances that were added or modified
          in the flush.
        """

        from .index import ArtifactReference
        del_index_ids = [obj.index_id() for obj in objects_deleted]
        deleted_aref_ids = [aref._id for aref in
                            ArtifactReference.query.find(dict(_id={'$in': del_index_ids}))]
        cls = self.__class__
        cls.to_add -= set(deleted_aref_ids)
        cls.to_delete |= set(del_index_ids)
        cls.to_add |= set([aref._id for aref in arefs_added])

    @classmethod
    def flush(cls):
        """
        Creates indexing tasks for cached adds and deletes, and resets the
        caches.

        .. warning:: This method is NOT called automatically when the parent
           session is flushed. It MUST be called explicitly.
        """
        # Post in chunks to avoid overflowing the max BSON document
        # size when the Monq task is created:
        # cls.to_delete - contains solr index ids which can easily be over
        #                 100 bytes. Here we allow for 160 bytes avg, plus
        #                 room for other document overhead.
        # cls.to_add - contains BSON ObjectIds, which are 12 bytes each, so
        #              we can easily put 1m in a doc with room left over.
        if cls.to_delete:
            for chunk in chunked_list(list(cls.to_delete), 100 * 1000):
                cls._post(index_tasks.del_artifacts, chunk)

        if cls.to_add:
            for chunk in chunked_list(list(cls.to_add), 1000 * 1000):
                cls._post(index_tasks.add_artifacts, chunk)
        cls.to_delete = set()
        cls.to_add = set()

    @classmethod
    def _post(cls, task_func, chunk):
        """
        Post task, recursively splitting and re-posting if the resulting
        mongo document is too large.
        """
        try:
            task_func.post(chunk)
        except pymongo.errors.InvalidDocument as e:
            # there are many types of InvalidDocument, only recurse if its
            # expected to help
            if str(e).startswith('BSON document too large'):
                cls._post(task_func, chunk[:len(chunk) // 2])
                cls._post(task_func, chunk[len(chunk) // 2:])
            else:
                raise


@contextmanager
def substitute_extensions(session, extensions=None):
    """
    Temporarily replace the extensions on a
    :class:`ming.odm.session.ThreadLocalODMSession` session.
    """
    original_exts = session._kwargs.get('extensions', [])

    def _set_exts(exts):
        session.flush()
        session.close()
        session._kwargs['extensions'] = exts
    _set_exts(extensions or [])
    yield session
    _set_exts(original_exts)


main_doc_session = Session.by_name('main')
project_doc_session = Session.by_name('project')
task_doc_session = Session.by_name('task')
main_orm_session = ThreadLocalORMSession(main_doc_session)
project_orm_session = ThreadLocalORMSession(project_doc_session)
task_orm_session = ThreadLocalORMSession(task_doc_session)
artifact_orm_session = ThreadLocalORMSession(
    doc_session=project_doc_session,
    extensions=[ArtifactSessionExtension])
repository_orm_session = ThreadLocalORMSession(
    doc_session=main_doc_session,
    extensions=[])
