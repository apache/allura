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

from ming import Session
from ming.orm.base import state
from ming.orm.ormsession import ThreadLocalORMSession, SessionExtension

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
        else: # pragma no cover
            st = state(obj)
            if st.status == st.new:
                self.objects_added = [ obj ]
            elif st.status == st.dirty:
                self.objects_modified = [ obj ]
            elif st.status == st.deleted:
                self.objects_deleted = [ obj ]

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
                    ArtifactReference.from_artifact(obj)
                    for obj in self.objects_added + self.objects_modified ]
                for obj in self.objects_added + self.objects_modified:
                    Shortlink.from_artifact(obj)
                # Flush shortlinks
                main_orm_session.flush()
            except Exception:
                log.exception("Failed to update artifact references. Is this a borked project migration?")
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
        from allura.tasks import index_tasks
        if objects_deleted:
            index_tasks.del_artifacts.post(
                [obj.index_id() for obj in objects_deleted])
        if arefs:
            index_tasks.add_artifacts.post([aref._id for aref in arefs])

main_doc_session = Session.by_name('main')
project_doc_session = Session.by_name('project')
task_doc_session = Session.by_name('task')
main_orm_session = ThreadLocalORMSession(main_doc_session)
project_orm_session = ThreadLocalORMSession(project_doc_session)
task_orm_session = ThreadLocalORMSession(task_doc_session)
artifact_orm_session = ThreadLocalORMSession(
    doc_session=project_doc_session,
    extensions = [ ArtifactSessionExtension ])
repository_orm_session = ThreadLocalORMSession(
    doc_session=main_doc_session,
    extensions = [  ])
